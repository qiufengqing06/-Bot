"""
Group settings database operations.
Extracted from agent_chat.py for better maintainability.
"""
from typing import Optional, Tuple

from nonebot_agent.config import config
from nonebot_agent.database import SessionLocal
from nonebot_agent.models import GroupSettings


def get_group_settings(group_id: str) -> Optional[GroupSettings]:
    """Get group settings from database."""
    db = SessionLocal()
    try:
        return db.query(GroupSettings).filter(GroupSettings.group_id == group_id).first()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def set_group_free_chat(group_id: str, enabled: bool, updated_by: str, probability: Optional[int] = None) -> GroupSettings:
    """Set group free chat mode."""
    db = SessionLocal()
    try:
        settings = db.query(GroupSettings).filter(GroupSettings.group_id == group_id).first()
        if settings:
            settings.free_chat_enabled = enabled
            settings.updated_by = updated_by
            if probability is not None:
                settings.reply_probability = probability
        else:
            settings = GroupSettings(
                group_id=group_id,
                free_chat_enabled=enabled,
                reply_probability=probability if probability is not None else config.FREE_CHAT_DEFAULT_PROBABILITY,
                updated_by=updated_by
            )
            db.add(settings)
        db.commit()
        db.refresh(settings)
        return settings
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def is_free_chat_enabled(group_id: str) -> Tuple[bool, int]:
    """Check if free chat is enabled for a group.
    
    Returns:
        Tuple of (enabled, reply_probability)
    """
    settings = get_group_settings(group_id)
    if settings:
        return settings.free_chat_enabled, settings.reply_probability
    return False, config.FREE_CHAT_DEFAULT_PROBABILITY
