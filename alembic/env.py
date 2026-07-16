"""Alembic migration environment for NoneBot Agent.

Reads DB_URL from .env (via dotenv) so credentials never appear in alembic.ini.
"""
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

# ---------------------------------------------------------------------------
# Load .env from project root so DB_URL is available before config parsing
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

import os  # noqa: E402  (must come after load_dotenv)

# ---------------------------------------------------------------------------
# Import ORM Base and all models so their tables are registered on metadata
# ---------------------------------------------------------------------------
from nonebot_agent.database import Base  # noqa: E402
from nonebot_agent.models import (  # noqa: E402, F401
    BotEmotionState,
    Conversation,
    ConversationSummary,
    GroupSettings,
    MemoryEvent,
    MemoryFact,
    Message,
    MessageMedia,
)

# this is the Alembic Config object
config = context.config

# Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Get database URL from environment (preferred) or fallback to config module
_db_url = os.environ.get("DB_URL")
if not _db_url:
    try:
        from nonebot_agent.config import config as _app_config
        _db_url = _app_config.DB_URL
    except Exception:
        _db_url = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    if not _db_url:
        raise RuntimeError("DB_URL not found in environment or config")
    
    context.configure(
        url=_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    if not _db_url:
        raise RuntimeError("DB_URL not found in environment or config")
    
    connectable = create_engine(
        _db_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
