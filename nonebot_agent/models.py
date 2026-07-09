"""
Database Models
SQLAlchemy ORM models for conversation and message storage.
Enhanced with mode support, group message tracking, and media support.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, Boolean
from sqlalchemy.orm import relationship

from nonebot_agent.database import Base


class Conversation(Base):
    """Conversation session table
    
    For group chats: one conversation per group (shared by all users)
    For C2C: one conversation per user
    """
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, index=True, comment="QQ User ID (for C2C) or 'group' marker")
    session_type = Column(String(20), nullable=False, comment="c2c or group")
    group_id = Column(String(128), nullable=True, index=True, comment="Group ID for group messages")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_user_session", "user_id", "session_type"),
        Index("idx_group", "group_id"),
    )
    
    def __repr__(self):
        return f"<Conversation(id={self.id}, user_id={self.user_id}, type={self.session_type})>"


class Message(Base):
    """Message record table
    
    Enhanced with:
    - sender_id: Track who sent the message in group chats
    - mode: Track which mode (chat/professional) the message belongs to
    - has_media: Flag for messages containing images/videos/files
    - is_bot_mentioned: Whether bot was mentioned in this message
    """
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, comment="user or assistant")
    content = Column(Text, nullable=False)
    sender_id = Column(String(128), nullable=True, index=True, comment="User ID who sent the message")
    mode = Column(String(20), default="professional", comment="chat or professional mode")
    has_media = Column(Boolean, default=False, comment="Whether message contains media")
    is_bot_mentioned = Column(Boolean, default=True, comment="Whether bot was mentioned")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    media = relationship("MessageMedia", back_populates="message", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_conv_created", "conversation_id", "created_at"),
        Index("idx_sender", "sender_id"),
        Index("idx_mode", "mode"),
    )
    
    def __repr__(self):
        return f"<Message(id={self.id}, role={self.role}, sender={self.sender_id}, mode={self.mode}, has_media={self.has_media})>"


class MessageMedia(Base):
    """Media attachments for messages (images, videos, files)"""
    __tablename__ = "message_media"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    media_type = Column(String(20), nullable=False, comment="image, video, or file")
    file_path = Column(String(512), nullable=True, comment="Local storage path")
    original_url = Column(Text, nullable=True, comment="Original URL")
    file_name = Column(String(255), nullable=True, comment="Original filename")
    file_size = Column(Integer, nullable=True, comment="File size in bytes")
    embedding_id = Column(String(128), nullable=True, comment="Chroma embedding ID for image")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    message = relationship("Message", back_populates="media")
    
    __table_args__ = (
        Index("idx_message_media", "message_id"),
        Index("idx_media_type", "media_type"),
    )
    
    def __repr__(self):
        return f"<MessageMedia(id={self.id}, type={self.media_type}, path={self.file_path})>"


class GroupSettings(Base):
    """Group chat settings
    
    Stores per-group settings including free chat mode toggle.
    """
    __tablename__ = "group_settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(128), unique=True, nullable=False, index=True, comment="QQ Group ID")
    free_chat_enabled = Column(Boolean, default=False, comment="Whether free chat mode is enabled")
    reply_probability = Column(Integer, default=30, comment="Reply probability percentage (0-100)")
    updated_by = Column(String(128), nullable=True, comment="QQ ID of last modifier")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_group_settings_group", "group_id"),
    )
    
    def __repr__(self):
        return f"<GroupSettings(group_id={self.group_id}, free_chat={self.free_chat_enabled}, prob={self.reply_probability}%)>"


class BotEmotionState(Base):
    """Bot emotion state per context (user or group)
    
    Uses PAD (Pleasure-Arousal-Dominance) model.
    - C2C: one emotion state per user
    - Group: one emotion state per group (shared)
    """
    __tablename__ = "bot_emotion_state"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    context_type = Column(String(20), nullable=False, comment="c2c or group")
    context_id = Column(String(128), nullable=False, comment="user_id or group_id")
    pleasure = Column(Integer, default=0, comment="Pleasure (-100~100): happy vs sad")
    arousal = Column(Integer, default=0, comment="Arousal (-100~100): excited vs calm")
    dominance = Column(Integer, default=0, comment="Dominance (-100~100): confident vs submissive")
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("idx_emotion_context", "context_type", "context_id", unique=True),
    )
    
    def __repr__(self):
        return f"<BotEmotionState({self.context_type}:{self.context_id} P={self.pleasure} A={self.arousal} D={self.dominance})>"


class MemoryFact(Base):
    """Structured long-term fact memory for a user."""
    __tablename__ = "memory_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, index=True, comment="QQ User ID")
    fact_key = Column(String(64), nullable=False, comment="Stable fact slot key")
    category = Column(String(32), nullable=False, comment="profile/preference/etc.")
    content = Column(Text, nullable=False, comment="Human-readable fact text")
    normalized_content = Column(Text, nullable=False, comment="Normalized content for dedupe")
    source_mode = Column(String(20), nullable=True, comment="chat or professional")
    source_group_id = Column(String(128), nullable=True, comment="Group where the fact was observed")
    chroma_id = Column(String(128), nullable=True, index=True, comment="Linked Chroma document id")
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_memory_fact_user_key", "user_id", "fact_key", unique=True),
        Index("idx_memory_fact_user_updated", "user_id", "updated_at"),
    )

    def __repr__(self):
        return f"<MemoryFact(user_id={self.user_id}, fact_key={self.fact_key}, category={self.category})>"


class MemoryEvent(Base):
    """Structured recent/episodic memory for a user."""
    __tablename__ = "memory_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, index=True, comment="QQ User ID")
    category = Column(String(32), nullable=False, comment="status/event/etc.")
    content = Column(Text, nullable=False, comment="Human-readable event text")
    normalized_content = Column(Text, nullable=False, comment="Normalized content for dedupe")
    source_mode = Column(String(20), nullable=True, comment="chat or professional")
    source_group_id = Column(String(128), nullable=True, index=True, comment="Optional group context")
    chroma_id = Column(String(128), nullable=True, index=True, comment="Linked Chroma document id")
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_memory_event_user_updated", "user_id", "updated_at"),
        Index("idx_memory_event_group_updated", "source_group_id", "updated_at"),
    )

    def __repr__(self):
        return f"<MemoryEvent(user_id={self.user_id}, category={self.category}, group={self.source_group_id})>"


class ConversationSummary(Base):
    """Rolling summary for a conversation per mode."""
    __tablename__ = "conversation_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    mode = Column(String(20), nullable=False, default="professional", comment="chat or professional mode")
    summary = Column(Text, nullable=False, comment="Rolling session summary")
    source_message_count = Column(Integer, default=0, nullable=False, comment="How many messages were summarized")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    conversation = relationship("Conversation")

    __table_args__ = (
        Index("idx_summary_conversation_mode", "conversation_id", "mode", unique=True),
    )

    def __repr__(self):
        return f"<ConversationSummary(conversation_id={self.conversation_id}, mode={self.mode})>"

