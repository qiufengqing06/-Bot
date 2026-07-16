"""
Database Migration Script (DEPRECATED)

.. deprecated::
    This script is deprecated. Use Alembic for schema migrations instead.

    Alembic provides versioned, reversible migrations that are safer and
    easier to review. See:

        alembic upgrade head      # Apply all pending migrations
        alembic revision --autogenerate -m "description"  # Generate new migration
        alembic current           # Show current revision
        alembic history           # Show migration history

    This script is kept only for backward compatibility with existing
    deployments. New migrations should be created with Alembic.
"""
from nonebot_agent.database import engine
from sqlalchemy import text

def migrate():
    """Add new columns to existing tables."""
    with engine.connect() as conn:
        # Add columns to messages table
        try:
            conn.execute(text("""
                ALTER TABLE messages 
                ADD COLUMN has_media BOOLEAN DEFAULT FALSE COMMENT 'Whether message contains media'
            """))
            print("Added has_media column to messages")
        except Exception as e:
            if "Duplicate column" in str(e):
                print("has_media column already exists")
            else:
                print(f"Error adding has_media: {e}")
        
        try:
            conn.execute(text("""
                ALTER TABLE messages 
                ADD COLUMN is_bot_mentioned BOOLEAN DEFAULT TRUE COMMENT 'Whether bot was mentioned'
            """))
            print("Added is_bot_mentioned column to messages")
        except Exception as e:
            if "Duplicate column" in str(e):
                print("is_bot_mentioned column already exists")
            else:
                print(f"Error adding is_bot_mentioned: {e}")
        
        # Create message_media table if not exists
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS message_media (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    message_id INT NOT NULL,
                    media_type VARCHAR(20) NOT NULL COMMENT 'image, video, or file',
                    file_path VARCHAR(512) COMMENT 'Local storage path',
                    original_url TEXT COMMENT 'Original URL',
                    file_name VARCHAR(255) COMMENT 'Original filename',
                    file_size INT COMMENT 'File size in bytes',
                    embedding_id VARCHAR(128) COMMENT 'Chroma embedding ID for image',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                    INDEX idx_message_media (message_id),
                    INDEX idx_media_type (media_type)
                )
            """))
            print("Created message_media table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("message_media table already exists")
            else:
                print(f"Error creating message_media: {e}")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    fact_key VARCHAR(64) NOT NULL,
                    category VARCHAR(32) NOT NULL,
                    content TEXT NOT NULL,
                    normalized_content TEXT NOT NULL,
                    source_mode VARCHAR(20) NULL,
                    source_group_id VARCHAR(128) NULL,
                    chroma_id VARCHAR(128) NULL,
                    last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY idx_memory_fact_user_key (user_id, fact_key),
                    INDEX idx_memory_fact_user_updated (user_id, updated_at),
                    INDEX idx_memory_fact_chroma (chroma_id)
                )
            """))
            print("Created memory_facts table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("memory_facts table already exists")
            else:
                print(f"Error creating memory_facts: {e}")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS memory_events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    category VARCHAR(32) NOT NULL,
                    content TEXT NOT NULL,
                    normalized_content TEXT NOT NULL,
                    source_mode VARCHAR(20) NULL,
                    source_group_id VARCHAR(128) NULL,
                    chroma_id VARCHAR(128) NULL,
                    last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_memory_event_user_updated (user_id, updated_at),
                    INDEX idx_memory_event_group_updated (source_group_id, updated_at),
                    INDEX idx_memory_event_chroma (chroma_id)
                )
            """))
            print("Created memory_events table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("memory_events table already exists")
            else:
                print(f"Error creating memory_events: {e}")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    conversation_id INT NOT NULL,
                    mode VARCHAR(20) NOT NULL DEFAULT 'professional',
                    summary TEXT NOT NULL,
                    source_message_count INT NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY idx_summary_conversation_mode (conversation_id, mode),
                    CONSTRAINT fk_summary_conversation FOREIGN KEY (conversation_id)
                        REFERENCES conversations(id) ON DELETE CASCADE
                )
            """))
            print("Created conversation_summaries table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("conversation_summaries table already exists")
            else:
                print(f"Error creating conversation_summaries: {e}")
        
        conn.commit()
        print("Migration completed!")

if __name__ == "__main__":
    migrate()
