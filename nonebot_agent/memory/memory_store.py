"""
Structured memory persistence and retrieval helpers.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from nonebot.log import logger
from sqlalchemy.orm import Session

from nonebot_agent.memory.memory_deduper import MemoryDeduper
from nonebot_agent.memory.memory_writer import MemoryCandidate, MemoryWriter
from nonebot_agent.models import MemoryEvent, MemoryFact

if TYPE_CHECKING:
    from langchain_core.documents import Document
    from nonebot_agent.memory.chroma_memory import ChromaMemory
else:
    Document = Any
    ChromaMemory = Any


class StructuredMemoryStore:
    def __init__(
        self,
        chroma: ChromaMemory,
        writer: Optional[MemoryWriter] = None,
        deduper: Optional[MemoryDeduper] = None,
    ):
        self.chroma = chroma
        self.writer = writer or MemoryWriter()
        self.deduper = deduper or MemoryDeduper()
        self._llm_client = None

    def _get_llm_client(self):
        """Lazy initialize OpenAI client for contradiction detection."""
        if self._llm_client is None:
            try:
                from openai import OpenAI
                from nonebot_agent.config import config
                self._llm_client = OpenAI(
                    api_key=config.LLM_API_KEY,
                    base_url=config.LLM_API_URL,
                )
            except Exception as exc:
                logger.warning(f"[MemoryStore] Failed to initialize LLM client: {exc}")
                self._llm_client = None
        return self._llm_client

    def _check_contradiction(self, old_content: str, new_content: str) -> bool:
        """
        Check if new content contradicts old content.
        
        Uses LLM to detect contradictions, with keyword fallback.
        Returns True if new contradicts old (should replace).
        """
        # Keyword-based fallback: negation words in new but not in old
        negation_words = ["不", "没", "戒", "放弃", "改", "不再", "停止"]
        has_negation_in_new = any(word in new_content for word in negation_words)
        has_negation_in_old = any(word in old_content for word in negation_words)
        
        if has_negation_in_new and not has_negation_in_old:
            # New contains negation, old doesn't - likely a change/contradiction
            return True

        # Try LLM-based contradiction detection
        client = self._get_llm_client()
        if client is None:
            return False

        from nonebot_agent.config import config
        
        prompt = f"这两条关于用户的信息是否矛盾？\nold: '{old_content}'\nnew: '{new_content}'\n回答YES或NO"

        try:
            result = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个判断信息是否矛盾的助手，只回答YES或NO。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=10,
            )
            answer = (result.choices[0].message.content or "").strip().upper()
            return "YES" in answer
        except Exception as exc:
            logger.debug(f"[MemoryStore] Contradiction check failed: {exc}")
            return False

    def write_candidates(
        self,
        db: Session,
        user_id: str,
        candidates: List[MemoryCandidate],
        group_id: Optional[str] = None,
        source_mode: Optional[str] = None,
    ) -> None:
        for candidate in candidates:
            if candidate.memory_type == "fact":
                self.upsert_fact(db, user_id, candidate, group_id=group_id, source_mode=source_mode)
            else:
                self.add_event(db, user_id, candidate, group_id=group_id, source_mode=source_mode)

    def upsert_fact(
        self,
        db: Session,
        user_id: str,
        candidate: MemoryCandidate,
        group_id: Optional[str] = None,
        source_mode: Optional[str] = None,
    ) -> MemoryFact:
        normalized = self.writer.normalize_text(candidate.text)
        now = datetime.utcnow()
        fact_key = candidate.slot_key or candidate.category
        record = db.query(MemoryFact).filter(
            MemoryFact.user_id == user_id,
            MemoryFact.fact_key == fact_key,
        ).first()

        if record:
            # Check if new content contradicts old content
            is_contradiction = self._check_contradiction(record.content, candidate.text)
            
            should_replace = is_contradiction or (
                not self.deduper.is_near_duplicate(
                    record.normalized_content, normalized, threshold=0.90
                ) or len(normalized) > len(record.normalized_content)
            )
            record.last_seen_at = now
            record.source_mode = source_mode or record.source_mode
            record.source_group_id = group_id or record.source_group_id
            if should_replace:
                if is_contradiction:
                    logger.info(f"[MemoryStore] Contradiction detected: '{record.content}' -> '{candidate.text}'")
                self._delete_chroma(record.chroma_id)
                record.content = candidate.text
                record.normalized_content = normalized
                record.category = candidate.category
                db.flush()
                record.chroma_id = self._save_chroma(
                    memory_type="fact",
                    user_id=user_id,
                    content=record.content,
                    memory_id=record.id,
                    category=record.category,
                    slot_key=record.fact_key,
                    group_id=group_id,
                    source_mode=source_mode,
                )
            return record

        record = MemoryFact(
            user_id=user_id,
            fact_key=fact_key,
            category=candidate.category,
            content=candidate.text,
            normalized_content=normalized,
            source_mode=source_mode,
            source_group_id=group_id,
            last_seen_at=now,
        )
        db.add(record)
        db.flush()
        record.chroma_id = self._save_chroma(
            memory_type="fact",
            user_id=user_id,
            content=record.content,
            memory_id=record.id,
            category=record.category,
            slot_key=record.fact_key,
            group_id=group_id,
            source_mode=source_mode,
        )
        return record

    def add_event(
        self,
        db: Session,
        user_id: str,
        candidate: MemoryCandidate,
        group_id: Optional[str] = None,
        source_mode: Optional[str] = None,
    ) -> MemoryEvent:
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
                    self._delete_chroma(record.chroma_id)
                    record.content = candidate.text
                    record.normalized_content = normalized
                    record.category = candidate.category
                    db.flush()
                    record.chroma_id = self._save_chroma(
                        memory_type="event",
                        user_id=user_id,
                        content=record.content,
                        memory_id=record.id,
                        category=record.category,
                        group_id=group_id,
                        source_mode=source_mode,
                    )
                return record

        record = MemoryEvent(
            user_id=user_id,
            category=candidate.category,
            content=candidate.text,
            normalized_content=normalized,
            source_mode=source_mode,
            source_group_id=group_id,
            last_seen_at=now,
        )
        db.add(record)
        db.flush()
        record.chroma_id = self._save_chroma(
            memory_type="event",
            user_id=user_id,
            content=record.content,
            memory_id=record.id,
            category=record.category,
            group_id=group_id,
            source_mode=source_mode,
        )
        return record

    def search_facts(
        self,
        user_id: str,
        query: str,
        limit: int,
        source_mode: Optional[str] = None,
    ) -> List[Document]:
        return self.chroma.search_memory(
            user_id=user_id,
            query=query,
            mode=source_mode,
            k=max(limit * 2, limit),
            extra_filters={"memory_type": "fact"},
        )

    def search_events(
        self,
        user_id: str,
        query: str,
        limit: int,
        group_id: Optional[str] = None,
        source_mode: Optional[str] = None,
    ) -> List[Document]:
        extra_filters = {"memory_type": "event"}
        if group_id:
            extra_filters["group_id"] = group_id
        return self.chroma.search_memory(
            user_id=user_id,
            query=query,
            mode=source_mode,
            k=max(limit * 2, limit),
            extra_filters=extra_filters,
        )

    def _save_chroma(
        self,
        memory_type: str,
        user_id: str,
        content: str,
        memory_id: int,
        category: str,
        slot_key: Optional[str] = None,
        group_id: Optional[str] = None,
        source_mode: Optional[str] = None,
    ) -> str:
        metadata = {
            "memory_type": memory_type,
            "category": category,
            "memory_id": str(memory_id),
        }
        if slot_key:
            metadata["slot_key"] = slot_key
        if source_mode:
            metadata["source_mode"] = source_mode
        return self.chroma.add_memory(
            user_id=user_id,
            content=content,
            mode=source_mode or "chat",
            group_id=group_id,
            metadata=metadata,
            doc_id=f"{memory_type}_{memory_id}",
        )

    def _delete_chroma(self, chroma_id: Optional[str]) -> None:
        if chroma_id:
            self.chroma.delete_memory(chroma_id)
