"""Memory summary manager - extracts summary writing logic."""
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from nonebot.log import logger
from nonebot_agent.models import MemoryFact, MemoryEvent


class SummaryWriter:
    """Handles writing conversation summaries to database."""
    
    def __init__(self, writer, deduper, chroma_available: bool, store):
        """
        Args:
            writer: MemoryWriter instance
            deduper: Memory deduper instance
            chroma_available: Whether ChromaDB is available
            store: StructuredMemoryStore instance
        """
        self.writer = writer
        self.deduper = deduper
        self.chroma_available = chroma_available
        self.store = store
    
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
            db: Database session
            user_id: User's ID
            user_message: User's message
            assistant_response: Assistant's response
            mode: Agent mode
            group_id: Optional group ID
            
        Returns:
            Comma-separated candidate texts
        """
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
        except Exception as exc:
            logger.warning(f"[Memory] Failed to save conversation summary: {exc}")
            return ""
        
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
