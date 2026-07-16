"""
NoneBot Agent Configuration Module
Uses pydantic-settings for typed, validated configuration.
All environment variables are loaded from .env automatically.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root for resolving relative paths
PROJECT_ROOT = Path(__file__).parent.parent


def _mask_key(value: Optional[str]) -> str:
    """Mask API key for display: show first 3 and last 4 chars."""
    if not value:
        return "(未设置)"
    s = str(value).strip()
    if not s:
        return "(未设置)"
    if len(s) <= 8:
        return s[:2] + "***"
    return s[:3] + "***" + s[-4:]


class Config(BaseSettings):
    """Configuration for NoneBot Agent with pydantic validation.

    All fields use UPPERCASE names for backward compatibility.
    Environment variables are matched case-insensitively.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===========================================
    # Main LLM Settings (只需修改这几个就能切换后端)
    # ===========================================
    LLM_MODEL: str = Field(default="claude-opus-4-5", description="主 LLM 模型名")
    LLM_API_KEY: Optional[str] = Field(default=None, description="主 LLM API Key")
    LLM_API_URL: str = Field(
        default="https://api.openai.com/v1", description="OpenAI-compatible base URL"
    )
    # 是否是多模态模型（能直接理解图片）
    # False 时会用 VISION_MODEL 先分析图片再发给 LLM
    IS_MULTIMODAL_MODEL: bool = Field(default=True, description="是否多模态模型")

    # ===========================================
    # Vision Model (当 IS_MULTIMODAL_MODEL=False 时使用)
    # ===========================================
    VISION_MODEL: str = Field(default="qwen3-vl-plus", description="视觉模型名")
    VISION_API_KEY: Optional[str] = Field(default=None, description="视觉模型 API Key")
    VISION_API_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="视觉模型 base URL",
    )

    # ===========================================
    # Qianwen/DashScope (用于向量嵌入)
    # ===========================================
    QIANWEN_API_KEY: Optional[str] = Field(
        default=None, description="DashScope API Key for embeddings"
    )
    DASHSCOPE_API_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MULTIMODAL_EMBEDDING_MODEL: str = "qwen2.5-vl-embedding"
    TEXT_EMBEDDING_MODEL: str = "text-embedding-v4"

    # ===========================================
    # Database & Storage
    # ===========================================
    DB_URL: str = Field(
        default="mysql+pymysql://root:***@localhost:3306/nonebot_agent?charset=utf8mb4",
        description="MySQL connection string",
    )
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "data" / "chroma")
    CHROMA_COLLECTION_NAME: str = "nonebot_agent_memory"
    IMAGE_STORAGE_DIR: str = str(PROJECT_ROOT / "data" / "images")  # 聊天图片
    IMAGE_RETENTION_DAYS: int = Field(default=7, ge=0)
    STICKER_STORAGE_DIR: str = str(
        PROJECT_ROOT / "data" / "images" / "stickers"
    )  # 表情包存储目录
    VIDEO_DOWNLOAD_DIR: str = str(PROJECT_ROOT / "data" / "videos")  # 视频下载目录
    VIDEO_DOWNLOAD_ENABLED: bool = True

    # ===========================================
    # Memory Settings
    # ===========================================
    SHORT_TERM_MEMORY_SIZE: int = Field(default=40, ge=1)
    GROUP_SHORT_TERM_MEMORY_SIZE: int = Field(default=80, ge=1)
    LONG_TERM_MEMORY_TOP_K: int = Field(default=20, ge=1)
    MEMORY_FACT_TOP_K: int = Field(default=6, ge=1)
    MEMORY_EVENT_TOP_K: int = Field(default=6, ge=1)
    MEMORY_SUMMARY_TRIGGER_MESSAGES: int = Field(default=6, ge=1)
    MEMORY_SUMMARY_SOURCE_LIMIT: int = Field(default=12, ge=1)
    MEMORY_EXTRACTION_ENABLED: bool = True

    # ===========================================
    # Other LLM Settings
    # ===========================================
    LLM_TEMPERATURE: float = Field(default=0.5, ge=0.0, le=2.0)
    LLM_CHAT_TEMPERATURE: float = Field(default=1.15, ge=0.0, le=2.0)
    CHAT_MODE_MAX_MESSAGES: int = Field(default=5, ge=1)
    CHAT_MODE_MESSAGE_DELAY: tuple[float, float] = (0.5, 1.5)
    CHAT_MAX_FOLLOWUPS: int = Field(default=1, ge=0)
    CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS: int = Field(default=1200, ge=0)
    CHAT_DELAY_BASE_MS: int = Field(default=180, ge=0)
    CHAT_DELAY_PER_CHAR_MS: int = Field(default=28, ge=0)
    CHAT_DELAY_JITTER_MS: int = Field(default=320, ge=0)

    # ===========================================
    # Skill Compatibility Layer
    # ===========================================
    SKILLS_ENABLED: bool = True
    SKILLS_DIR: str = str(PROJECT_ROOT / "data" / "skills")
    SKILLS_AUTO_LOAD: bool = True
    SKILLS_MAX_ACTIVE: int = Field(default=8, ge=1)
    SKILLS_PROMPT_MAX_CHARS: int = Field(default=6000, ge=1)
    SKILLS_REFERENCE_TOP_K: int = Field(default=4, ge=1)
    SKILLS_REFERENCE_MAX_CHARS: int = Field(default=5000, ge=1)
    SKILLS_REFERENCE_MAX_FILE_CHARS: int = Field(default=20000, ge=1)
    SKILLS_REFERENCE_CHUNK_CHARS: int = Field(default=1200, ge=1)
    SKILLS_TOOL_TIMEOUT_SECONDS: int = Field(default=30, ge=1)
    SKILLS_STATE_FILE: str = str(
        PROJECT_ROOT / "data" / "skills" / ".skill_state.json"
    )
    SKILLS_PREFIX_ALIASES: str = "E:ai-li-xi-ya,e:ai-li-xi-ya"
    SKILL_EXCLUSIVE_CHAT_MAX_FOLLOWUPS: int = Field(default=3, ge=1)
    SKILLS_SCRIPT_PYTHON: str = sys.executable
    SKILLS_SCRIPT_ALLOWLIST: str = ""
    SKILLS_SCRIPT_TIMEOUT_SECONDS: int = Field(default=10, ge=1)
    SKILLS_SCRIPT_MAX_OUTPUT_CHARS: int = Field(default=8000, ge=1)
    SKILLS_ALLOW_MCP: bool = False
    SKILLS_ALLOW_OPENAPI: bool = True
    SKILLS_ALLOW_LOCAL_CODE: bool = False
    SKILLS_REQUIRE_MASTER_CONFIRM_HIGH_RISK: bool = True
    DEFAULT_CHAT_PERSONA: str = "tian-yu-xue"

    # ===========================================
    # Free Chat Mode Settings (群聊自由聊天模式)
    # ===========================================
    FREE_CHAT_DEFAULT_PROBABILITY: int = Field(
        default=30, ge=0, le=100, description="默认回复概率 (0-100)"
    )
    FREE_CHAT_SILENT_CHANCE: float = Field(
        default=0.1, ge=0.0, le=1.0, description="沉默概率"
    )

    # ===========================================
    # Bot Master Settings (主人设置)
    # ===========================================
    MASTER_QQ: str = ""  # 主人QQ号，可以使用重启等高级命令
    INDIVIDUAL_QQ: str = ""
    GROUP_QQ: str = ""
    PROACTIVE_DAY_START_HOUR: int = Field(default=9, ge=0, le=23)
    PROACTIVE_DAY_END_HOUR: int = Field(default=23, ge=0, le=23)
    PROACTIVE_PRIVATE_MIN_INTERVAL_MINUTES: int = Field(default=240, ge=0)
    PROACTIVE_PRIVATE_MAX_INTERVAL_MINUTES: int = Field(default=720, ge=0)
    PROACTIVE_GROUP_MIN_INTERVAL_MINUTES: int = Field(default=360, ge=0)
    PROACTIVE_GROUP_MAX_INTERVAL_MINUTES: int = Field(default=960, ge=0)
    PROACTIVE_ONLINE_TOPIC_PROBABILITY: float = Field(default=0.55, ge=0.0, le=1.0)

    # ===========================================
    # Optional Integrations (warned if missing at startup)
    # ===========================================
    WEB_SEARCH_API_KEY: Optional[str] = None
    WEB_SEARCH_API_URL: Optional[str] = None
    DOUBAO_API_KEY: Optional[str] = None
    DOUBAO_API_URL: Optional[str] = None

    # ===========================================
    # Validators
    # ===========================================

    @field_validator(
        "LLM_API_URL", "VISION_API_URL", "DASHSCOPE_API_URL", mode="before"
    )
    @classmethod
    def validate_http_url(cls, v: str) -> str:
        """Validate that URL fields are valid HTTP(S) URLs."""
        if not v:
            return v
        from pydantic import HttpUrl

        try:
            HttpUrl(v)
        except Exception:
            raise ValueError(f"Invalid HTTP URL: {v}")
        return v

    @field_validator("SKILLS_DIR", "SKILLS_STATE_FILE", mode="before")
    @classmethod
    def resolve_project_path(cls, v: str) -> str:
        """Resolve relative paths against PROJECT_ROOT."""
        if not v:
            return v
        path = Path(v)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path)

    @model_validator(mode="after")
    def set_fallbacks(self) -> "Config":
        """Set fallback values for fields that depend on other fields."""
        # VISION_API_KEY falls back to QIANWEN_API_KEY
        if not self.VISION_API_KEY and self.QIANWEN_API_KEY:
            self.VISION_API_KEY = self.QIANWEN_API_KEY
        # SKILLS_SCRIPT_PYTHON falls back to sys.executable
        if not self.SKILLS_SCRIPT_PYTHON:
            self.SKILLS_SCRIPT_PYTHON = sys.executable
        return self


def config_report(cfg: "Config | None" = None) -> str:
    """Generate a startup configuration report with masked secrets.

    Returns a multi-line string summarizing key configuration values
    without leaking API keys or passwords.
    """
    if cfg is None:
        cfg = config

    lines = ["=== NoneBot Agent 配置 ==="]

    # LLM
    lines.append(
        f"LLM: {cfg.LLM_MODEL} @ {cfg.LLM_API_URL} (key: {_mask_key(cfg.LLM_API_KEY)})"
    )

    # Vision
    multimodal = "True" if cfg.IS_MULTIMODAL_MODEL else "False"
    lines.append(f"VISION: {cfg.VISION_MODEL} (multimodal: {multimodal})")

    # DB — mask password in connection string
    db_display = _mask_db_url(cfg.DB_URL)
    lines.append(f"DB: {db_display}")

    # Memory
    mem_status = "enabled" if cfg.MEMORY_EXTRACTION_ENABLED else "disabled"
    lines.append(f"MEMORY_EXTRACTION: {mem_status}")

    # Skills
    if cfg.SKILLS_ENABLED:
        lines.append(f"SKILLS: enabled (max_active={cfg.SKILLS_MAX_ACTIVE})")
    else:
        lines.append("SKILLS: disabled")

    # Optional integrations
    if cfg.WEB_SEARCH_API_KEY:
        lines.append(
            f"WEB_SEARCH: configured (key: {_mask_key(cfg.WEB_SEARCH_API_KEY)})"
        )
    else:
        lines.append("WEB_SEARCH: not configured")

    if cfg.DOUBAO_API_KEY:
        lines.append(
            f"IMAGE_GEN: configured (key: {_mask_key(cfg.DOUBAO_API_KEY)})"
        )
    else:
        lines.append("IMAGE_GEN: not configured")

    lines.append("=== 配置检查完毕 ===")
    return "\n".join(lines)


def _mask_db_url(url: str) -> str:
    """Mask password in a SQLAlchemy/database URL for display."""
    if "@" not in url:
        return url
    before_at, after_at = url.rsplit("@", 1)
    # Find the password portion: scheme://user:password
    scheme_end = before_at.find("://")
    if scheme_end == -1:
        return url
    user_part = before_at[scheme_end + 3 :]
    colon_idx = user_part.rfind(":")
    if colon_idx == -1:
        return url
    user = user_part[:colon_idx]
    scheme = before_at[: scheme_end + 3]
    return f"{scheme}{user}:***@{after_at}"


# Singleton
config = Config()
