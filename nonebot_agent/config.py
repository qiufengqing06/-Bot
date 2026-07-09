"""
NoneBot Agent Configuration Module
Load environment variables and provide unified configuration access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import sys
from pathlib import Path
import dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
dotenv.load_dotenv(PROJECT_ROOT / ".env")


def _project_path_from_env(env_name: str, default: Path) -> str:
    raw_value = os.getenv(env_name)
    if not raw_value:
        return str(default)
    path = Path(raw_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


@dataclass
class ConfigValidationResult:
    """Result object for runtime configuration validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _require_value(cfg: object, name: str, errors: list[str], reason: str) -> None:
    if _is_blank(getattr(cfg, name, None)):
        errors.append(f"{name} is required: {reason}")


def _warn_if_missing(
    cfg: object,
    names: list[str],
    warnings: list[str],
    consequence: str,
) -> None:
    missing = [name for name in names if _is_blank(getattr(cfg, name, None))]
    if missing:
        warnings.append(f"{', '.join(missing)} missing: {consequence}")


def _require_non_negative_int(cfg: object, name: str, errors: list[str]) -> None:
    value = getattr(cfg, name, None)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        errors.append(f"{name} must be a non-negative integer")


def validate_runtime_config(cfg: object = None) -> ConfigValidationResult:
    """
    Validate configuration needed for normal bot startup.

    The validation is intentionally static. It checks presence and value ranges
    without opening network connections or touching the database.
    """
    cfg = cfg or config
    errors: list[str] = []
    warnings: list[str] = []

    _require_value(cfg, "LLM_MODEL", errors, "main chat model name")
    _require_value(cfg, "LLM_API_KEY", errors, "main chat model API key")
    _require_value(cfg, "LLM_API_URL", errors, "OpenAI-compatible base URL")
    _require_value(cfg, "DB_URL", errors, "MySQL connection string")
    _require_value(cfg, "QIANWEN_API_KEY", errors, "DashScope embeddings for Chroma memory")

    if not bool(getattr(cfg, "IS_MULTIMODAL_MODEL", False)):
        _require_value(cfg, "VISION_MODEL", errors, "vision model for text-only main LLM")
        _require_value(cfg, "VISION_API_KEY", errors, "vision model API key")
        _require_value(cfg, "VISION_API_URL", errors, "vision model base URL")

    for name in [
        "CHAT_DELAY_BASE_MS",
        "CHAT_DELAY_PER_CHAR_MS",
        "CHAT_DELAY_JITTER_MS",
        "CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS",
        "CHAT_MAX_FOLLOWUPS",
    ]:
        _require_non_negative_int(cfg, name, errors)

    private_min = getattr(cfg, "PROACTIVE_PRIVATE_MIN_INTERVAL_MINUTES", 0)
    private_max = getattr(cfg, "PROACTIVE_PRIVATE_MAX_INTERVAL_MINUTES", 0)
    group_min = getattr(cfg, "PROACTIVE_GROUP_MIN_INTERVAL_MINUTES", 0)
    group_max = getattr(cfg, "PROACTIVE_GROUP_MAX_INTERVAL_MINUTES", 0)
    for name, value in [
        ("PROACTIVE_PRIVATE_MIN_INTERVAL_MINUTES", private_min),
        ("PROACTIVE_PRIVATE_MAX_INTERVAL_MINUTES", private_max),
        ("PROACTIVE_GROUP_MIN_INTERVAL_MINUTES", group_min),
        ("PROACTIVE_GROUP_MAX_INTERVAL_MINUTES", group_max),
    ]:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"{name} must be a non-negative integer")
    if isinstance(private_min, int) and isinstance(private_max, int) and private_min > private_max:
        errors.append("PROACTIVE_PRIVATE interval invalid: min interval cannot exceed max interval")
    if isinstance(group_min, int) and isinstance(group_max, int) and group_min > group_max:
        errors.append("PROACTIVE_GROUP interval invalid: min interval cannot exceed max interval")

    online_probability = getattr(cfg, "PROACTIVE_ONLINE_TOPIC_PROBABILITY", 0)
    if not isinstance(online_probability, (int, float)) or isinstance(online_probability, bool):
        errors.append("PROACTIVE_ONLINE_TOPIC_PROBABILITY must be a number between 0 and 1")
    elif online_probability < 0 or online_probability > 1:
        errors.append("PROACTIVE_ONLINE_TOPIC_PROBABILITY must be between 0 and 1")

    if bool(getattr(cfg, "SKILLS_ALLOW_LOCAL_CODE", False)):
        _require_value(cfg, "SKILLS_SCRIPT_PYTHON", errors, "python executable for local skill scripts")
        _warn_if_missing(
            cfg,
            ["SKILLS_SCRIPT_ALLOWLIST"],
            warnings,
            "local code execution is enabled but no scripts are allowlisted",
        )

    _warn_if_missing(
        cfg,
        ["WEB_SEARCH_API_KEY", "WEB_SEARCH_API_URL"],
        warnings,
        "web search tool will be unavailable",
    )
    _warn_if_missing(
        cfg,
        ["DOUBAO_API_KEY", "DOUBAO_API_URL"],
        warnings,
        "image generation command will be unavailable",
    )
    _warn_if_missing(
        cfg,
        ["MASTER_QQ"],
        warnings,
        "owner-only commands such as restart and emotion override will be unavailable",
    )

    return ConfigValidationResult(errors=errors, warnings=warnings)


def format_config_validation_report(result: ConfigValidationResult) -> str:
    """Format validation errors and warnings for console output."""
    if result.ok and not result.warnings:
        return "配置校验通过。"

    lines = ["NoneBot Agent 配置校验结果"]
    if result.errors:
        lines.append("")
        lines.append("配置错误:")
        lines.extend(f"- {item}" for item in result.errors)
    if result.warnings:
        lines.append("")
        lines.append("配置警告:")
        lines.extend(f"- {item}" for item in result.warnings)
    return "\n".join(lines)


class Config:
    """Configuration class for NoneBot Agent"""
    
    # ===========================================
    # Main LLM Settings (只需修改这几个就能切换后端)
    # ===========================================
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-4-5")
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_API_URL = os.getenv("LLM_API_URL", "https://api.openai.com/v1")
    
    # 是否是多模态模型（能直接理解图片）
    # False 时会用 VISION_MODEL 先分析图片再发给 LLM
    IS_MULTIMODAL_MODEL = os.getenv("IS_MULTIMODAL_MODEL", "true").lower() == "true"
    
    # ===========================================
    # Vision Model (当 IS_MULTIMODAL_MODEL=False 时使用)
    # ===========================================
    VISION_MODEL = os.getenv("VISION_MODEL", "qwen3-vl-plus")
    VISION_API_KEY = os.getenv("VISION_API_KEY") or os.getenv("QIANWEN_API_KEY")
    VISION_API_URL = os.getenv("VISION_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    # ===========================================
    # Qianwen/DashScope (用于向量嵌入)
    # ===========================================
    QIANWEN_API_KEY = os.getenv("QIANWEN_API_KEY")
    DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MULTIMODAL_EMBEDDING_MODEL = "qwen2.5-vl-embedding"
    TEXT_EMBEDDING_MODEL = "text-embedding-v4"
    
    # ===========================================
    # Database & Storage
    # ===========================================
    DB_URL = os.getenv("DB_URL", "mysql+pymysql://root:12345@localhost:3306/nonebot_agent?charset=utf8mb4")
    CHROMA_PERSIST_DIR = str(PROJECT_ROOT / "data" / "chroma")
    CHROMA_COLLECTION_NAME = "nonebot_agent_memory"
    IMAGE_STORAGE_DIR = str(PROJECT_ROOT / "data" / "images") # 聊天图片
    IMAGE_RETENTION_DAYS = 7
    STICKER_STORAGE_DIR = str(PROJECT_ROOT / "data" / "images" / "stickers")  # 表情包存储目录
    
    # Video Download Settings
    VIDEO_DOWNLOAD_DIR = str(PROJECT_ROOT / "data" / "videos")  # 视频下载目录
    VIDEO_DOWNLOAD_ENABLED = os.getenv("VIDEO_DOWNLOAD_ENABLED", "true").lower() == "true"
    
    # ===========================================
    # Memory Settings
    # ===========================================
    SHORT_TERM_MEMORY_SIZE = 40
    GROUP_SHORT_TERM_MEMORY_SIZE = 80
    LONG_TERM_MEMORY_TOP_K = 20
    MEMORY_FACT_TOP_K = 6
    MEMORY_EVENT_TOP_K = 6
    MEMORY_SUMMARY_TRIGGER_MESSAGES = 6
    MEMORY_SUMMARY_SOURCE_LIMIT = 12
    
    # ===========================================
    # Other LLM Settings
    # ===========================================
    LLM_TEMPERATURE = 0.5
    LLM_CHAT_TEMPERATURE = 1.15
    CHAT_MODE_MAX_MESSAGES = 5
    CHAT_MODE_MESSAGE_DELAY = (0.5, 1.5)
    CHAT_MAX_FOLLOWUPS = int(os.getenv("CHAT_MAX_FOLLOWUPS", "1"))
    CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS = int(os.getenv("CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS", "1200"))
    CHAT_DELAY_BASE_MS = int(os.getenv("CHAT_DELAY_BASE_MS", "180"))
    CHAT_DELAY_PER_CHAR_MS = int(os.getenv("CHAT_DELAY_PER_CHAR_MS", "28"))
    CHAT_DELAY_JITTER_MS = int(os.getenv("CHAT_DELAY_JITTER_MS", "320"))

    # ===========================================
    # Skill Compatibility Layer
    # ===========================================
    SKILLS_ENABLED = os.getenv("SKILLS_ENABLED", "true").lower() == "true"
    SKILLS_DIR = _project_path_from_env("SKILLS_DIR", PROJECT_ROOT / "data" / "skills")
    SKILLS_AUTO_LOAD = os.getenv("SKILLS_AUTO_LOAD", "true").lower() == "true"
    SKILLS_MAX_ACTIVE = int(os.getenv("SKILLS_MAX_ACTIVE", "8"))
    SKILLS_PROMPT_MAX_CHARS = int(os.getenv("SKILLS_PROMPT_MAX_CHARS", "6000"))
    SKILLS_REFERENCE_TOP_K = int(os.getenv("SKILLS_REFERENCE_TOP_K", "4"))
    SKILLS_REFERENCE_MAX_CHARS = int(os.getenv("SKILLS_REFERENCE_MAX_CHARS", "5000"))
    SKILLS_REFERENCE_MAX_FILE_CHARS = int(os.getenv("SKILLS_REFERENCE_MAX_FILE_CHARS", "20000"))
    SKILLS_REFERENCE_CHUNK_CHARS = int(os.getenv("SKILLS_REFERENCE_CHUNK_CHARS", "1200"))
    SKILLS_TOOL_TIMEOUT_SECONDS = int(os.getenv("SKILLS_TOOL_TIMEOUT_SECONDS", "30"))
    SKILLS_STATE_FILE = _project_path_from_env(
        "SKILLS_STATE_FILE", PROJECT_ROOT / "data" / "skills" / ".skill_state.json"
    )
    SKILLS_PREFIX_ALIASES = os.getenv("SKILLS_PREFIX_ALIASES", "E:ai-li-xi-ya,e:ai-li-xi-ya")
    SKILL_EXCLUSIVE_CHAT_MAX_FOLLOWUPS = int(os.getenv("SKILL_EXCLUSIVE_CHAT_MAX_FOLLOWUPS", "3"))
    SKILLS_SCRIPT_PYTHON = os.getenv("SKILLS_SCRIPT_PYTHON") or sys.executable
    SKILLS_SCRIPT_ALLOWLIST = os.getenv("SKILLS_SCRIPT_ALLOWLIST", "")
    SKILLS_SCRIPT_TIMEOUT_SECONDS = int(os.getenv("SKILLS_SCRIPT_TIMEOUT_SECONDS", "10"))
    SKILLS_SCRIPT_MAX_OUTPUT_CHARS = int(os.getenv("SKILLS_SCRIPT_MAX_OUTPUT_CHARS", "8000"))
    SKILLS_ALLOW_MCP = os.getenv("SKILLS_ALLOW_MCP", "false").lower() == "true"
    SKILLS_ALLOW_OPENAPI = os.getenv("SKILLS_ALLOW_OPENAPI", "true").lower() == "true"
    SKILLS_ALLOW_LOCAL_CODE = os.getenv("SKILLS_ALLOW_LOCAL_CODE", "false").lower() == "true"
    SKILLS_REQUIRE_MASTER_CONFIRM_HIGH_RISK = (
        os.getenv("SKILLS_REQUIRE_MASTER_CONFIRM_HIGH_RISK", "true").lower() == "true"
    )
    
    # ===========================================
    # Free Chat Mode Settings (群聊自由聊天模式)
    # ===========================================
    FREE_CHAT_DEFAULT_PROBABILITY = 30  # 默认回复概率 (0-100)
    
    # ===========================================
    # Bot Master Settings (主人设置)
    # ===========================================
    MASTER_QQ = os.getenv("MASTER_QQ", "")  # 主人QQ号，可以使用重启等高级命令
    INDIVIDUAL_QQ = os.getenv("INDIVIDUAL_QQ", "")
    GROUP_QQ = os.getenv("GROUP_QQ", "")
    PROACTIVE_DAY_START_HOUR = int(os.getenv("PROACTIVE_DAY_START_HOUR", "9"))
    PROACTIVE_DAY_END_HOUR = int(os.getenv("PROACTIVE_DAY_END_HOUR", "23"))
    PROACTIVE_PRIVATE_MIN_INTERVAL_MINUTES = int(os.getenv("PROACTIVE_PRIVATE_MIN_INTERVAL_MINUTES", "240"))
    PROACTIVE_PRIVATE_MAX_INTERVAL_MINUTES = int(os.getenv("PROACTIVE_PRIVATE_MAX_INTERVAL_MINUTES", "720"))
    PROACTIVE_GROUP_MIN_INTERVAL_MINUTES = int(os.getenv("PROACTIVE_GROUP_MIN_INTERVAL_MINUTES", "360"))
    PROACTIVE_GROUP_MAX_INTERVAL_MINUTES = int(os.getenv("PROACTIVE_GROUP_MAX_INTERVAL_MINUTES", "960"))
    PROACTIVE_ONLINE_TOPIC_PROBABILITY = float(os.getenv("PROACTIVE_ONLINE_TOPIC_PROBABILITY", "0.55"))


config = Config()
