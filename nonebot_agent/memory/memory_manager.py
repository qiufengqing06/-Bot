"""Memory manager - coordinates memory operations."""
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from nonebot.log import logger
from nonebot_agent.models import Conversation, Message
from nonebot_agent.memory.memory_context_formatter import format_memories_as_context, format_time_context
from nonebot_agent.memory.memory_summary_manager import SummaryWriter


class MemoryManager:
    """
    Unified memory manager that coordinates:
    - Short-term memory: Recent conversation messages
    - Long-term memory: Semantic memory from ChromaDB
    - Summary writing: Conversation summary extraction
    """
    
    def __init__(self):
        """Initialize memory manager with all dependencies."""
        from nonebot_agent.memory.chroma_memory import ChromaMemory
        from nonebot_agent.memory.memory_writer import MemoryWriter
        from nonebot_agent.memory.memory_store import StructuredMemoryStore
        from nonebot_agent.memory.memory_deduper import MemoryDeduper
        
        # Initialize ChromaDB
        try:
            self.chroma = ChromaMemory()
            chroma_available = True
        except Exception as e:
            logger.warning(f"[Memory] ChromaDB initialization failed: {e}")
            self.chroma = None
            chroma_available = False
        
        # Initialize other dependencies
        self.writer = MemoryWriter()
        self.deduper = MemoryDeduper()
        self.store = StructuredMemoryStore(self.chroma, self.deduper)  # type: ignore[arg-type]
        self.chroma_available = chroma_available
        self.summary_writer = SummaryWriter(self.writer, self.deduper, chroma_available, self.store)
        self._seen_memories = set()
    
    def get_or_create_conversation(
        self,
        db: Session,
        user_id: str,
        session_type: str,
        group_id: Optional[str] = None
    ) -> Conversation:
        """Get existing conversation or create a new one."""
        from nonebot_agent.models import Conversation
        
        if session_type == "group" and group_id:
            query = db.query(Conversation).filter(
                Conversation.session_type == "group",
                Conversation.group_id == group_id
            )
        else:
            query = db.query(Conversation).filter(
                Conversation.user_id == user_id,
                Conversation.session_type == "c2c"
            )
        
        conversation = query.first()
        
        if not conversation:
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
        """Add a message to the conversation."""
        from datetime import datetime
        from nonebot_agent.models import Message, MessageMedia
        
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
        db.flush()
        
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
    ) -> List:
        """Get recent messages from the conversation as LangChain messages."""
        from langchain_core.messages import HumanMessage, AIMessage
        from nonebot_agent.config import config
        from nonebot_agent.models import Message
        
        limit = limit or config.SHORT_TERM_MEMORY_SIZE
        
        query = db.query(Message).filter(
            Message.conversation_id == conversation.id
        )
        
        if mode:
            query = query.filter(Message.mode == mode)
        
        messages = query.order_by(Message.created_at.desc()).limit(limit).all()
        messages = list(reversed(messages))
        
        langchain_messages = []
        for msg in messages:
            if msg.role == "user":
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
    ) -> List:
        """Get recent messages from a specific group."""
        from nonebot_agent.models import Conversation
        from nonebot_agent.config import config
        
        limit = limit or config.GROUP_SHORT_TERM_MEMORY_SIZE
        
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
    ) -> List:
        """Get recent messages from a user's C2C conversation."""
        from nonebot_agent.models import Conversation
        from nonebot_agent.config import config
        
        limit = limit or config.SHORT_TERM_MEMORY_SIZE
        
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
    ) -> List:
        """Get a user's message history from all group conversations."""
        from langchain_core.messages import HumanMessage, AIMessage
        from nonebot_agent.models import Message
        
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
        user_nickname: Optional[str] = None,
    ) -> str:
        """Retrieve relevant long-term memories and format as context."""
        from nonebot_agent.config import config
        
        self._seen_memories.clear()
        sections = []

        summary = self.summary_writer.writer.get_summary(db, conversation.id, mode or "professional")
        if summary and summary.summary:
            sections.append(f"[近期会话摘要:]\n- {summary.summary}")

        if not self.chroma_available:
            return "\n".join(sections)

        is_recall_query = self.writer.detect_memory_recall_trigger(query)
        fact_limit = config.MEMORY_FACT_TOP_K * 2 if is_recall_query else config.MEMORY_FACT_TOP_K
        event_limit = config.MEMORY_EVENT_TOP_K * 2 if is_recall_query else config.MEMORY_EVENT_TOP_K

        try:
            facts = self.store.search_facts(user_id, query, fact_limit, source_mode=mode)
            facts_text = format_memories_as_context(
                facts,
                "[相关用户事实:]",
                limit=fact_limit,
                user_nickname=user_nickname,
                seen_memories=self._seen_memories,
                normalize_text_func=self.writer.normalize_text,
                format_time_func=format_time_context,
            )
            if facts_text:
                sections.append(facts_text)

            events = self.store.search_events(user_id, query, event_limit, group_id=group_id, source_mode=mode)
            events_text = format_memories_as_context(
                events,
                "[相关用户经历与近况:]",
                limit=event_limit,
                user_nickname=user_nickname,
                seen_memories=self._seen_memories,
                normalize_text_func=self.writer.normalize_text,
                format_time_func=format_time_context,
            )
            if events_text:
                sections.append(events_text)
                
            if is_recall_query and (facts_text or events_text):
                recall_prefix = "用户正在问你关于他们自己的记忆。请自然地回忆和提及你记得的关于他们的事情，像是朋友间的聊天一样。\n\n"
                sections.insert(0, recall_prefix)
                
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
        user_nickname: Optional[str] = None,
    ) -> str:
        """Retrieve relevant long-term memories for a group and format as context."""
        from nonebot_agent.config import config
        
        self._seen_memories.clear()
        sections = []

        summary = self.summary_writer.writer.get_summary(db, conversation.id, mode or "professional")
        if summary and summary.summary:
            sections.append(f"[本群近期对话摘要:]\n- {summary.summary}")

        if not self.chroma_available:
            return "\n".join(sections)

        is_recall_query = self.writer.detect_memory_recall_trigger(query)
        fact_limit = config.MEMORY_FACT_TOP_K * 2 if is_recall_query else config.MEMORY_FACT_TOP_K
        event_limit = config.MEMORY_EVENT_TOP_K * 2 if is_recall_query else config.MEMORY_EVENT_TOP_K

        try:
            facts = self.store.search_facts(user_id, query, fact_limit, source_mode=mode)
            facts_text = format_memories_as_context(
                facts,
                "[当前用户相关事实:]",
                limit=fact_limit,
                user_nickname=user_nickname,
                seen_memories=self._seen_memories,
                normalize_text_func=self.writer.normalize_text,
                format_time_func=format_time_context,
            )
            if facts_text:
                sections.append(facts_text)

            events = self.store.search_events(user_id, query, event_limit, group_id=group_id, source_mode=mode)
            events_text = format_memories_as_context(
                events,
                "[当前用户在本群相关经历:]",
                limit=event_limit,
                user_nickname=user_nickname,
                seen_memories=self._seen_memories,
                normalize_text_func=self.writer.normalize_text,
                format_time_func=format_time_context,
            )
            if events_text:
                sections.append(events_text)
                
            if is_recall_query and (facts_text or events_text):
                recall_prefix = "用户正在问你关于他们自己的记忆。请自然地回忆和提及你记得的关于他们的事情，像是朋友间的聊天一样。\n\n"
                sections.insert(0, recall_prefix)
                
        except Exception as exc:
            logger.warning(f"[Memory] Chroma search failed in get_group_long_term_context: {exc}")

        return "\n".join(sections)
    
    def save_to_long_term(
        self,
        user_id: str,
        content: str,
        mode: str = "professional",
        group_id: Optional[str] = None,
        category: str = "conversation"
    ) -> str:
        """Save important information to long-term memory."""
        if not self.chroma_available:
            logger.debug("[Memory] Chroma unavailable, skipping long-term save")
            return ""
        
        try:
            if self.chroma is None:
                return ""
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
        """Save a conversation exchange to long-term memory."""
        return self.summary_writer.save_conversation_summary(
            db, user_id, user_message, assistant_response, mode, group_id
        )
    
    def record_group_message(
        self,
        user_id: str,
        group_id: str,
        content: str,
        has_media: bool = False,
        media_info: Optional[List[dict]] = None,
        is_bot_mentioned: bool = False,
        nickname: Optional[str] = None
    ):
        """Record a group message without triggering agent response."""
        from nonebot_agent.database import SessionLocal
        
        db = SessionLocal()
        try:
            conversation = self.get_or_create_conversation(db, user_id, "group", group_id)
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
    ) -> Tuple[Conversation, List, str]:
        """Process an incoming message and prepare context."""
        from nonebot_agent.database import SessionLocal
        from nonebot_agent.config import config
        
        db = SessionLocal()
        try:
            conversation = self.get_or_create_conversation(db, user_id, session_type, group_id)
            
            self.add_message(
                db, conversation, "user", user_message,
                sender_id=user_id, mode=mode,
                has_media=has_media, is_bot_mentioned=True,
                media_info=media_info
            )
            
            if session_type == "group" and group_id:
                short_term = self.get_short_term_memory(
                    db, conversation, mode=mode, 
                    limit=config.GROUP_SHORT_TERM_MEMORY_SIZE
                )
            else:
                short_term = self.get_short_term_memory(db, conversation, mode=mode)
            
            if session_type == "group" and group_id:
                long_term_context = self.get_group_long_term_context(
                    db, conversation, user_id, group_id, user_message, mode=mode
                )
            else:
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
        """Save assistant response to both MySQL and long-term memory."""
        from nonebot_agent.database import SessionLocal
        from nonebot_agent.models import Conversation, Message
        
        db = SessionLocal()
        try:
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()
            
            if conversation:
                if image_description and has_media:
                    last_user_msg = db.query(Message).filter(
                        Message.conversation_id == conversation_id,
                        Message.role == "user",
                        Message.has_media == True
                    ).order_by(Message.created_at.desc()).first()
                    
                    if last_user_msg:
                        original_content = last_user_msg.content
                        updated_content = f"[用户发送了图片: {image_description}] {original_content}".strip()
                        last_user_msg.content = updated_content
                        db.flush()
                        logger.info("[Memory] Updated user message with image description")
                
                self.add_message(
                    db, conversation, "assistant", response,
                    sender_id=None, mode=mode,
                    has_media=False, is_bot_mentioned=True
                )
                
                self.save_conversation_summary(
                    db, user_id, user_message, response,
                    mode=mode, group_id=group_id
                )
                
                if self.summary_writer.writer.structured_tables_ready:
                    self.summary_writer.writer.summary_manager.refresh_summary(db, conversation_id, mode)
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
        from nonebot_agent.database import SessionLocal
        
        db = SessionLocal()
        try:
            conversation = self.get_or_create_conversation(db, user_id, session_type, group_id)
            self.add_message(
                db, conversation, "assistant", content,
                sender_id=None, mode=mode,
                has_media=False, is_bot_mentioned=False,
            )
            if self.summary_writer.writer.structured_tables_ready:
                self.summary_writer.writer.summary_manager.refresh_summary(db, conversation.id, mode)
                db.commit()
            return conversation
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
