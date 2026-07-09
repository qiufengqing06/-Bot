"""
Rolling conversation summary manager.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from nonebot_agent.config import config
from nonebot_agent.memory.memory_writer import MemoryWriter
from nonebot_agent.models import ConversationSummary, Message

try:
    from nonebot.log import logger
except Exception:
    logger = logging.getLogger(__name__)


def _is_missing_table_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return (
        "doesn't exist" in lowered
        or "no such table" in lowered
        or "undefined table" in lowered
        or "1146" in lowered
    )


class MemorySummaryManager:
    def __init__(self, writer: Optional[MemoryWriter] = None):
        self.writer = writer or MemoryWriter()
        self.trigger_messages = config.MEMORY_SUMMARY_TRIGGER_MESSAGES
        self.source_limit = config.MEMORY_SUMMARY_SOURCE_LIMIT

    def get_summary(self, db: Session, conversation_id: int, mode: str) -> Optional[ConversationSummary]:
        try:
            return db.query(ConversationSummary).filter(
                ConversationSummary.conversation_id == conversation_id,
                ConversationSummary.mode == mode,
            ).first()
        except (ProgrammingError, OperationalError) as exc:
            if _is_missing_table_error(exc):
                logger.warning("[Memory] conversation_summaries table missing, summary retrieval skipped")
                return None
            raise

    def refresh_summary(self, db: Session, conversation_id: int, mode: str) -> Optional[ConversationSummary]:
        try:
            total_count = db.query(Message).filter(
                Message.conversation_id == conversation_id,
                Message.mode == mode,
            ).count()

            existing = self.get_summary(db, conversation_id, mode)
            if existing and total_count - existing.source_message_count < self.trigger_messages:
                return existing

            recent_messages = db.query(Message).filter(
                Message.conversation_id == conversation_id,
                Message.mode == mode,
            ).order_by(Message.created_at.desc()).limit(self.source_limit).all()
            recent_messages = list(reversed(recent_messages))

            summary_text = self.build_summary(recent_messages)
            if not summary_text:
                return existing

            if existing:
                existing.summary = summary_text
                existing.source_message_count = total_count
                return existing

            summary = ConversationSummary(
                conversation_id=conversation_id,
                mode=mode,
                summary=summary_text,
                source_message_count=total_count,
            )
            db.add(summary)
            db.flush()
            return summary
        except (ProgrammingError, OperationalError) as exc:
            if _is_missing_table_error(exc):
                logger.warning("[Memory] conversation_summaries table missing, summary update skipped")
                db.rollback()
                return None
            raise

    def build_summary(self, messages: List[Message]) -> str:
        if not messages:
            return ""

        recent_user_topics = []
        for msg in messages:
            if msg.role != "user":
                continue
            cleaned = self.writer.strip_transport_prefix(msg.content)
            if not cleaned:
                continue
            if cleaned.startswith("[用户发送了图片:"):
                cleaned = cleaned[:40]
            if len(cleaned) > 36:
                cleaned = cleaned[:36] + "..."
            if cleaned not in recent_user_topics:
                recent_user_topics.append(cleaned)

        if not recent_user_topics:
            return ""

        recent_user_topics = recent_user_topics[-4:]
        return "最近几轮主要在聊：" + "；".join(recent_user_topics)
