"""
Database Module
SQLAlchemy engine and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from nonebot_agent.config import config

# Create SQLAlchemy engine
engine = create_engine(
    config.DB_URL,
    echo=False,  # Set to True for SQL debugging
    pool_pre_ping=True,  # Enable connection health checks
    pool_recycle=3600,   # Recycle connections after 1 hour
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Get database session (dependency injection pattern)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database - create all tables"""
    from nonebot_agent.models import (
        Conversation,
        Message,
        GroupSettings,
        BotEmotionState,
        MessageMedia,
        MemoryFact,
        MemoryEvent,
        ConversationSummary,
    )  # Import models to register them
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")
