"""
Memory Manager Module
Unified memory management combining short-term and long-term memory.
Enhanced with mode-based separation and unified user memory across sessions.
"""
from datetime import datetime
from typing import List, Optional, Tuple

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.documents import Document
from nonebot.log import logger
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from nonebot_agent.config import config
from nonebot_agent.database import SessionLocal, engine
from nonebot_agent.memory.chroma_memory import ChromaMemory
from nonebot_agent.memory.memory_store import StructuredMemoryStore
from nonebot_agent.memory.memory_summary import MemorySummaryManager
from nonebot_agent.memory.memory_writer import MemoryWriter
from nonebot_agent.models import (
    Conversation,
    Message,
    MessageMedia,
    MemoryFact,
    MemoryEvent,
    ConversationSummary,
)


def _is_missing_table_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return (
        "doesn't exist" in lowered
        or "no such table" in lowered
        or "undefined table" in lowered
        or "1146" in lowered
    )


class MemoryManager:
    """
    Unified memory manager that handles:
    - Short-term memory: Recent conversation messages from MySQL
    - Long-term memory: Semantic memory from Chroma vector database
    
    Enhanced with:
    - Mode-based memory separation (chat vs professional)
    - Unified user memory across C2C and group sessions
    - Group context aggregation from multiple users
    """
    
    def __init__(self, chroma_memory: Optional[ChromaMemory] = None):
        """
        Initialize memory manager.
        
        Args:
            chroma_memory: Optional ChromaMemory instance (creates one if not provided)
        """
        # Try to initialize Chroma; fall back to MySQL-only if it fails.
        self.chroma_available = True
        self._chroma_init_error: Optional[str] = None
        if chroma_memory is not None:
            self.chroma = chroma_memory
        else:
            try:
                self.chroma = ChromaMemory()
            except Exception as exc:
                self.chroma = None
                self.chroma_available = False
                self._chroma_init_error = str(exc)
                logger.warning(
                    f"[Memory] ChromaDB unavailable, falling back to MySQL-only memory: {exc}"
                )
        self.writer = MemoryWriter()
        # StructuredMemoryStore needs a chroma handle; pass None when degraded.
        self.store = StructuredMemoryStore(self.chroma, self.writer)
        self.summary_manager = MemorySummaryManager(self.writer)
        self.short_term_size = config.SHORT_TERM_MEMORY_SIZE
        self.group_short_term_size = config.GROUP_SHORT_TERM_MEMORY_SIZE
        self.long_term_top_k = config.LONG_TERM_MEMORY_TOP_K
        self.fact_top_k = config.MEMORY_FACT_TOP_K
        self.event_top_k = config.MEMORY_EVENT_TOP_K
        self.structured_tables_ready = self._ensure_structured_memory_tables()

    def _ensure_structured_memory_tables(self) -> bool:
        """
        Best-effort schema guard for structured memory tables.
        Prevents runtime crashes if migrations were not executed yet.
        """
        try:
            MemoryFact.__table__.create(bind=engine, checkfirst=True)
            MemoryEvent.__table__.create(bind=engine, checkfirst=True)
            ConversationSummary.__table__.create(bind=engine, checkfirst=True)
            return True
        except Exception as exc:
            logger.warning(f"[Memory] Unable to ensure structured memory tables: {exc}")
            return False
    
    def get_or_create_conversation(
        self,
        db: Session,
        user_id: str,
        session_type: str,
        group_id: Optional[str] = None
    ) -> Conversation:
        """
        Get existing conversation or create a new one.
        
        For groups: Use group_id as the conversation identifier
        For C2C: Use user_id as the conversation identifier
        
        Args:
            db: Database session
            user_id: User's ID
            session_type: 'c2c' or 'group'
            group_id: Group ID for group messages
            
        Returns:
            Conversation object
        """
        if session_type == "group" and group_id:
            # For group chats, one conversation per group
            query = db.query(Conversation).filter(
                Conversation.session_type == "group",
                Conversation.group_id == group_id
            )
        else:
            # For C2C, one conversation per user
            query = db.query(Conversation).filter(
                Conversation.user_id == user_id,
                Conversation.session_type == "c2c"
            )
        
        conversation = query.first()
        
        if not conversation:
            # Create new conversation
            conversation = Conversation(
                user_id=user_id if session_type == "c2c" else "group",
                session_type=session_type,
                group_id=group_id
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
        
        return conversation
    
    def add_message(
        self,
        db: Session,
        conversation: Conversation,
        role: str,
        content: str,
        sender_id: Optional[str] = None,
        mode: str = "professional",
        has_media: bool = False,
        is_bot_mentioned: bool = True,
        media_info: Optional[List[dict]] = None
    ) -> Message:
        """
        Add a message to the conversation.
        
        Args:
            db: Database session
            conversation: Conversation object
            role: 'user' or 'assistant'
            content: Message content
            sender_id: User ID who sent the message
            mode: Agent mode ('chat' or 'professional')
            has_media: Whether message contains media
            is_bot_mentioned: Whether bot was mentioned
            media_info: List of media metadata dicts
            
        Returns:
            Message object
        """
        message = Message(
            conversation_id=conversation.id,
            role=role,
            content=content,
            sender_id=sender_id,
            mode=mode,
            has_media=has_media,
            is_bot_mentioned=is_bot_mentioned
        )
        db.add(message)
        db.flush()  # Get message ID
        
        # Add media records if present
        if media_info:
            for info in media_info:
                media = MessageMedia(
                    message_id=message.id,
                    media_type=info.get("type", "unknown"),
                    file_path=info.get("local_path"),
                    original_url=info.get("url"),
                    file_name=info.get("file_name")
                )
                db.add(media)
        
        # Update conversation timestamp
        conversation.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(message)
        
        return message
    
    def get_short_term_memory(
        self,
        db: Session,
        conversation: Conversation,
        mode: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[BaseMessage]:
        """
        Get recent messages from the conversation as LangChain messages.
        
        Args:
            db: Database session
            conversation: Conversation object
            mode: Optional mode filter
            limit: Number of messages to retrieve
            
        Returns:
            List of LangChain messages
        """
        limit = limit or self.short_term_size
        
        # Build query
        query = db.query(Message).filter(
            Message.conversation_id == conversation.id
        )
        
        # Filter by mode if specified
        if mode:
            query = query.filter(Message.mode == mode)
        
        # Get recent messages
        messages = query.order_by(Message.created_at.desc()).limit(limit).all()
        
        # Reverse to get chronological order
        messages = list(reversed(messages))
        
        # Convert to LangChain messages with sender info for group context
        langchain_messages = []
        for msg in messages:
            if msg.role == "user":
                # Include sender info in group messages
                if msg.sender_id and conversation.session_type == "group":
                    content = f"[用户{msg.sender_id[-4:]}]: {msg.content}"
                else:
                    content = msg.content
                langchain_messages.append(HumanMessage(content=content))
            else:
                langchain_messages.append(AIMessage(content=msg.content))
        
        return langchain_messages
    
    def get_group_short_term_memory(
        self,
        db: Session,
        group_id: str,
        mode: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[BaseMessage]:
        """
        Get recent messages from a specific group.
        
        Args:
            db: Database session
            group_id: Group ID
            mode: Optional mode filter
            limit: Number of messages to retrieve
            
        Returns:
            List of LangChain messages
        """
        limit = limit or self.group_short_term_size
        
        # Find group conversation
        conversation = db.query(Conversation).filter(
            Conversation.group_id == group_id,
            Conversation.session_type == "group"
        ).first()
        
        if not conversation:
            return []
        
        return self.get_short_term_memory(db, conversation, mode=mode, limit=limit)
    
    def get_user_short_term_memory(
        self,
        db: Session,
        user_id: str,
        mode: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[BaseMessage]:
        """
        Get recent messages from a user's C2C conversation.
        
        Args:
            db: Database session
            user_id: User ID
            mode: Optional mode filter
            limit: Number of messages to retrieve
            
        Returns:
            List of LangChain messages
        """
        limit = limit or self.short_term_size
        
        # Find user's C2C conversation
        conversation = db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.session_type == "c2c"
        ).first()
        
        if not conversation:
            return []
        
        return self.get_short_term_memory(db, conversation, mode=mode, limit=limit)
    
    def get_user_history_from_groups(
        self,
        db: Session,
        user_id: str,
        mode: Optional[str] = None,
        limit: int = 5
    ) -> List[BaseMessage]:
        """
        Get a user's message history from all group conversations.
        
        Args:
            db: Database session
            user_id: User ID
            mode: Optional mode filter
            limit: Number of messages to retrieve
            
        Returns:
            List of LangChain messages
        """
        # Query messages where this user is the sender
        query = db.query(Message).filter(
            Message.sender_id == user_id
        )
        
        if mode:
            query = query.filter(Message.mode == mode)
        
        messages = query.order_by(Message.created_at.desc()).limit(limit).all()
        messages = list(reversed(messages))
        
        langchain_messages = []
        for msg in messages:
            if msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            else:
                langchain_messages.append(AIMessage(content=msg.content))
        
        return langchain_messages
    
    def get_long_term_context(
        self,
        db: Session,
        conversation: Conversation,
        user_id: str,
        query: str,
        mode: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> str:
        """
        Retrieve relevant long-term memories and format as context.
        
        Args:
            user_id: User's ID
            query: Current query to search relevant memories
            mode: Optional mode filter
            k: Number of memories to retrieve
            
        Returns:
            Formatted context string
        """
        sections = []

        summary = self.summary_manager.get_summary(db, conversation.id, mode or "professional")
        if summary and summary.summary:
            sections.append(f"[近期会话摘要:]\n- {summary.summary}")

        # Skip Chroma-based retrieval if Chroma is unavailable
        if not self.chroma_available:
            return "\n".join(sections)

        try:
            facts = self.store.search_facts(
                user_id,
                query,
                self.fact_top_k,
                source_mode=mode,
            )
            facts_text = self._format_memories_as_context(facts, "[相关用户事实:]", limit=self.fact_top_k)
            if facts_text:
                sections.append(facts_text)

            events = self.store.search_events(
                user_id,
                query,
                self.event_top_k,
                group_id=group_id,
                source_mode=mode,
            )
            events_text = self._format_memories_as_context(events, "[相关用户经历与近况:]", limit=self.event_top_k)
            if events_text:
                sections.append(events_text)
        except Exception as exc:
            logger.warning(f"[Memory] Chroma search failed in get_long_term_context: {exc}")

        return "\n".join(sections)
    
    def get_group_long_term_context(
        self,
        db: Session,
        conversation: Conversation,
        user_id: str,
        group_id: str,
        query: str,
        mode: Optional[str] = None,
    ) -> str:
        """
        Retrieve relevant long-term memories for a group and format as context.
        
        Args:
            group_id: Group's ID
            query: Current query to search relevant memories
            mode: Optional mode filter
            k: Number of memories to retrieve
            
        Returns:
            Formatted context string
        """
        sections = []

        summary = self.summary_manager.get_summary(db, conversation.id, mode or "professional")
        if summary and summary.summary:
            sections.append(f"[本群近期对话摘要:]\n- {summary.summary}")

        # Skip Chroma-based retrieval if Chroma is unavailable
        if not self.chroma_available:
            return "\n".join(sections)

        try:
            facts = self.store.search_facts(
                user_id,
                query,
                self.fact_top_k,
                source_mode=mode,
            )
            facts_text = self._format_memories_as_context(facts, "[当前用户相关事实:]", limit=self.fact_top_k)
            if facts_text:
                sections.append(facts_text)

            events = self.store.search_events(
                user_id,
                query,
                self.event_top_k,
                group_id=group_id,
                source_mode=mode,
            )
            events_text = self._format_memories_as_context(events, "[当前用户在本群相关经历:]", limit=self.event_top_k)
            if events_text:
                sections.append(events_text)
        except Exception as exc:
            logger.warning(f"[Memory] Chroma search failed in get_group_long_term_context: {exc}")

        return "\n".join(sections)

    def _sanitize_memory_content(self, content: str) -> str:
        """Strip legacy answer-heavy phrasing so retrieval favors facts, not wording."""
        cleaned = content.strip()
        if cleaned.startswith("用户问:") and "回复:" in cleaned:
            cleaned = cleaned.split("回复:", 1)[0]
            cleaned = cleaned.replace("用户问:", "用户曾提到:", 1).strip()
        return cleaned

    def _format_memories_as_context(self, memories: List[Document], title: str, limit: Optional[int] = None) -> str:
        """Format retrieved memories with dedupe so the prompt sees facts instead of repeats."""
        if not memories:
            return ""

        context_parts = [title]
        seen = set()
        collected = 0

        for mem in memories:
            cleaned = self._sanitize_memory_content(mem.page_content)
            normalized = self.writer.normalize_text(cleaned)
            if not cleaned or normalized in seen:
                continue
            seen.add(normalized)
            timestamp = mem.metadata.get("timestamp", "Unknown time")
            context_parts.append(f"- ({timestamp}) {cleaned}")
            collected += 1
            if limit and collected >= limit:
                break

        return "\n".join(context_parts) if len(context_parts) > 1 else ""
    
    def save_to_long_term(
        self,
        user_id: str,
        content: str,
        mode: str = "professional",
        group_id: Optional[str] = None,
        category: str = "conversation"
    ) -> str:
        """
        Save important information to long-term memory.
        
        Args:
            user_id: User's ID
            content: Content to save
            mode: Agent mode
            group_id: Optional group ID
            category: Category of the memory
            
        Returns:
            Memory ID
        """
        if not self.chroma_available:
            logger.debug("[Memory] Chroma unavailable, skipping long-term save")
            return ""
        
        try:
            return self.chroma.add_memory(
                user_id=user_id,
                content=content,
                mode=mode,
                group_id=group_id,
                metadata={"category": category}
            )
        except Exception as exc:
            logger.warning(f"[Memory] Failed to save to Chroma: {exc}")
            return ""
    
    def save_conversation_summary(
        self,
        db: Session,
        user_id: str,
        user_message: str,
        assistant_response: str,
        mode: str = "professional",
        group_id: Optional[str] = None
    ) -> str:
        """
        Save a conversation exchange to long-term memory.
        
        Args:
            user_id: User's ID
            user_message: User's message
            assistant_response: Assistant's response
            mode: Agent mode
            group_id: Optional group ID
            
        Returns:
            Memory ID
        """
        if not self.structured_tables_ready:
            return ""

        candidates = self.writer.build_candidates(user_message)
        if not candidates:
            return ""

        try:
            # If Chroma is unavailable, only write to MySQL (skip vector embeddings)
            if not self.chroma_available:
                for candidate in candidates:
                    if candidate.memory_type == "fact":
                        self._write_fact_mysql_only(db, user_id, candidate, group_id=group_id, source_mode=mode)
                    else:
                        self._write_event_mysql_only(db, user_id, candidate, group_id=group_id, source_mode=mode)
            else:
                self.store.write_candidates(
                    db=db,
                    user_id=user_id,
                    candidates=candidates,
                    group_id=group_id,
                    source_mode=mode,
                )
        except (ProgrammingError, OperationalError) as exc:
            if _is_missing_table_error(exc):
                db.rollback()
                self.structured_tables_ready = False
                logger.warning("[Memory] Structured memory tables missing, skip writing structured memory this run")
                return ""
            raise
        return ",".join(candidate.text for candidate in candidates)
    
    def _write_fact_mysql_only(
        self,
        db: Session,
        user_id: str,
        candidate,
        group_id: Optional[str] = None,
        source_mode: Optional[str] = None,
    ):
        """Write fact to MySQL only (no Chroma)."""
        from nonebot_agent.models import MemoryFact
        from datetime import datetime
        normalized = self.writer.normalize_text(candidate.text)
        now = datetime.utcnow()
        fact_key = candidate.slot_key or candidate.category
        record = db.query(MemoryFact).filter(
            MemoryFact.user_id == user_id,
            MemoryFact.fact_key == fact_key,
        ).first()

        if record:
            should_replace = not self.deduper.is_near_duplicate(
                record.normalized_content, normalized, threshold=0.90
            ) or len(normalized) > len(record.normalized_content)
            record.last_seen_at = now
            record.source_mode = source_mode or record.source_mode
            record.source_group_id = group_id or record.source_group_id
            if should_replace:
                record.content = candidate.text
                record.normalized_content = normalized
                record.category = candidate.category
                record.chroma_id = None  # No Chroma
        else:
            record = MemoryFact(
                user_id=user_id,
                fact_key=fact_key,
                category=candidate.category,
                content=candidate.text,
                normalized_content=normalized,
                source_mode=source_mode,
                source_group_id=group_id,
                last_seen_at=now,
                chroma_id=None,  # No Chroma
            )
            db.add(record)
    
    def _write_event_mysql_only(
        self,
        db: Session,
        user_id: str,
        candidate,
        group_id: Optional[str] = None,
        source_mode: Optional[str] = None,
    ):
        """Write event to MySQL only (no Chroma)."""
        from nonebot_agent.models import MemoryEvent
        from datetime import datetime
        normalized = self.writer.normalize_text(candidate.text)
        now = datetime.utcnow()
        recent_records = db.query(MemoryEvent).filter(
            MemoryEvent.user_id == user_id
        ).order_by(MemoryEvent.last_seen_at.desc()).limit(8).all()

        for record in recent_records:
            same_group = record.source_group_id == group_id
            if same_group and self.deduper.is_near_duplicate(
                record.normalized_content, normalized, threshold=0.86
            ):
                record.last_seen_at = now
                if len(normalized) > len(record.normalized_content):
                    record.content = candidate.text
                    record.normalized_content = normalized
                    record.category = candidate.category
                    record.chroma_id = None  # No Chroma
                return

        record = MemoryEvent(
            user_id=user_id,
            category=candidate.category,
            content=candidate.text,
            normalized_content=normalized,
            source_mode=source_mode,
            source_group_id=group_id,
            last_seen_at=now,
            chroma_id=None,  # No Chroma
        )
        db.add(record)
    
    def record_group_message(
        self,
        user_id: str,
        group_id: str,
        content: str,
        has_media: bool = False,
        media_info: Optional[List[dict]] = None,
        is_bot_mentioned: bool = False,
        nickname: str = None
    ):
        """
        Record a group message without triggering agent response.
        Used to track group chat context even when bot is not mentioned.
        
        Args:
            user_id: User's ID
            group_id: Group ID
            content: Message content (already includes nickname in format)
            has_media: Whether message contains media
            media_info: List of media metadata
            is_bot_mentioned: Whether bot was mentioned
            nickname: User's nickname (for logging/future use)
        """
        db = SessionLocal()
        try:
            # Get or create group conversation
            conversation = self.get_or_create_conversation(
                db, user_id, "group", group_id
            )
            
            # Add message to database (mode=chat for group context messages)
            self.add_message(
                db, conversation, "user", content,
                sender_id=user_id, mode="chat",
                has_media=has_media, is_bot_mentioned=is_bot_mentioned,
                media_info=media_info
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    def process_message(
        self,
        user_id: str,
        user_message: str,
        session_type: str = "c2c",
        group_id: Optional[str] = None,
        mode: str = "professional",
        has_media: bool = False,
        media_info: Optional[List[dict]] = None
    ) -> Tuple[Conversation, List[BaseMessage], str]:
        """
        Process an incoming message and prepare context.
        
        For group messages:
        - Gets group's recent messages (all users)
        - Also retrieves user's personal history (C2C + group)
        
        For C2C messages:
        - Gets user's recent messages
        
        Args:
            user_id: User's ID
            user_message: The user's message
            session_type: 'c2c' or 'group'
            group_id: Group ID for group messages
            mode: Agent mode
            has_media: Whether message contains media
            media_info: List of media metadata
            
        Returns:
            Tuple of (conversation, short_term_messages, long_term_context)
        """
        db = SessionLocal()
        try:
            # Get or create conversation
            conversation = self.get_or_create_conversation(
                db, user_id, session_type, group_id
            )
            
            # Add user message to database
            self.add_message(
                db, conversation, "user", user_message,
                sender_id=user_id, mode=mode,
                has_media=has_media, is_bot_mentioned=True,
                media_info=media_info
            )
            
            # Get short-term memory based on session type
            if session_type == "group" and group_id:
                # For groups: only get group messages (not C2C messages)
                short_term = self.get_short_term_memory(
                    db, conversation, mode=mode, 
                    limit=self.group_short_term_size
                )
            else:
                # For C2C: just user's messages
                short_term = self.get_short_term_memory(
                    db, conversation, mode=mode
                )
            
            # Get long-term context (mode-filtered, group-separated for group chats)
            if session_type == "group" and group_id:
                # For groups: search only by group_id, not user_id
                long_term_context = self.get_group_long_term_context(
                    db, conversation, user_id, group_id, user_message, mode=mode
                )
            else:
                # For C2C: search by user_id
                long_term_context = self.get_long_term_context(
                    db, conversation, user_id, user_message, mode=mode
                )
            
            return conversation, short_term, long_term_context
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    def save_response(
        self,
        conversation_id: int,
        user_id: str,
        user_message: str,
        response: str,
        mode: str = "professional",
        group_id: Optional[str] = None,
        has_media: bool = False,
        image_description: str = ""
    ):
        """
        Save assistant response to both MySQL and long-term memory.
        Also updates the user message with image description if available.
        
        Args:
            conversation_id: Conversation ID
            user_id: User's ID
            user_message: Original user message (may include image description)
            response: Assistant's response
            mode: Agent mode
            group_id: Optional group ID
            has_media: Whether the user message had media
            image_description: Description of image(s) from vision model
        """
        db = SessionLocal()
        try:
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()
            
            if conversation:
                # If there's an image description, update the last user message in MySQL
                if image_description and has_media:
                    # Find the most recent user message in this conversation
                    last_user_msg = db.query(Message).filter(
                        Message.conversation_id == conversation_id,
                        Message.role == "user",
                        Message.has_media == True
                    ).order_by(Message.created_at.desc()).first()
                    
                    if last_user_msg:
                        # Update the content to include image description
                        original_content = last_user_msg.content
                        updated_content = f"[用户发送了图片: {image_description}] {original_content}".strip()
                        last_user_msg.content = updated_content
                        db.flush()
                        logger.info("[Memory] Updated user message with image description")
                
                # Save assistant response to MySQL
                self.add_message(
                    db, conversation, "assistant", response,
                    sender_id=None, mode=mode,
                    has_media=False, is_bot_mentioned=True
                )
                
                # Save user-centric memory instead of whole Q/A pairs.
                # This avoids retrieving old assistant wording and causing repeated replies.
                self.save_conversation_summary(
                    db, user_id, user_message, response,
                    mode=mode, group_id=group_id
                )
                if self.structured_tables_ready:
                    self.summary_manager.refresh_summary(db, conversation_id, mode)
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def record_assistant_message(
        self,
        user_id: str,
        content: str,
        session_type: str = "c2c",
        group_id: Optional[str] = None,
        mode: str = "chat",
    ) -> Optional[Conversation]:
        """Persist a bot-initiated assistant message without requiring a user turn."""
        db = SessionLocal()
        try:
            conversation = self.get_or_create_conversation(db, user_id, session_type, group_id)
            self.add_message(
                db,
                conversation,
                "assistant",
                content,
                sender_id=None,
                mode=mode,
                has_media=False,
                is_bot_mentioned=False,
            )
            if self.structured_tables_ready:
                self.summary_manager.refresh_summary(db, conversation.id, mode)
                db.commit()
            return conversation
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
