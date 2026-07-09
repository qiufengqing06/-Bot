"""Startup configuration validation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from nonebot_agent.config import config as default_config


@dataclass(frozen=True)
class ConfigIssue:
    """A startup configuration issue."""

    level: str
    key: str
    message: str
    feature: str = "core"


class RuntimeConfigError(RuntimeError):
    """Raised when required startup configuration is missing or invalid."""

    def __init__(self, issues: Iterable[ConfigIssue]):
        self.issues = [issue for issue in issues if issue.level == "error"]
        super().__init__(format_config_issues(self.issues))


def validate_runtime_config(config_obj=default_config) -> List[ConfigIssue]:
    """Validate runtime configuration without touching external services."""
    issues: List[ConfigIssue] = []

    _require(issues, config_obj, "LLM_MODEL", "主 LLM 模型名不能为空。")
    _require(issues, config_obj, "LLM_API_KEY", "主 LLM API key 不能为空。")
    _require(issues, config_obj, "LLM_API_URL", "主 LLM API base URL 不能为空。")
    _require(issues, config_obj, "QIANWEN_API_KEY", "长期记忆和表情包向量检索需要 QIANWEN_API_KEY。")
    _require(issues, config_obj, "DB_URL", "MySQL DB_URL 不能为空。")

    if not bool(getattr(config_obj, "IS_MULTIMODAL_MODEL", True)):
        _require(issues, config_obj, "VISION_MODEL", "文本主模型模式下需要配置视觉模型名。", feature="vision")
        _require(issues, config_obj, "VISION_API_KEY", "文本主模型模式下需要配置 VISION_API_KEY。", feature="vision")
        _require(issues, config_obj, "VISION_API_URL", "文本主模型模式下需要配置 VISION_API_URL。", feature="vision")

    _warn_if_missing(
        issues,
        config_obj,
        "WEB_SEARCH_API_KEY",
        "未配置 WEB_SEARCH_API_KEY，网络搜索工具会降级或不可用。",
        feature="search",
    )
    _warn_if_missing(
        issues,
        config_obj,
        "WEB_SEARCH_API_URL",
        "未配置 WEB_SEARCH_API_URL，网络搜索工具会降级或不可用。",
        feature="search",
    )
    _warn_if_missing(
        issues,
        config_obj,
        "DOUBAO_API_KEY",
        "未配置 DOUBAO_API_KEY，/画图 命令不可用。",
        feature="image_generation",
    )
    _warn_if_missing(
        issues,
        config_obj,
        "DOUBAO_API_URL",
        "未配置 DOUBAO_API_URL，/画图 命令不可用。",
        feature="image_generation",
    )

    if bool(getattr(config_obj, "SKILLS_ALLOW_LOCAL_CODE", False)):
        _require(
            issues,
            config_obj,
            "SKILLS_SCRIPT_PYTHON",
            "启用本地脚本 Skill 时必须配置 SKILLS_SCRIPT_PYTHON。",
            feature="skills",
        )
        _warn_if_missing(
            issues,
            config_obj,
            "SKILLS_SCRIPT_ALLOWLIST",
            "已启用本地脚本 Skill，但 SKILLS_SCRIPT_ALLOWLIST 为空，不会注册任何脚本。",
            feature="skills",
        )

    return issues


def assert_runtime_config(config_obj=default_config) -> List[ConfigIssue]:
    """Raise when required config is invalid, return all issues otherwise."""
    issues = validate_runtime_config(config_obj)
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        raise RuntimeConfigError(errors)
    return issues


def format_config_issues(issues: Iterable[ConfigIssue]) -> str:
    """Format configuration issues for startup logs and exceptions."""
    items = list(issues)
    if not items:
        return "配置检查通过。"

    lines = ["启动配置检查发现问题："]
    for issue in items:
        prefix = "ERROR" if issue.level == "error" else "WARN"
        lines.append(f"- [{prefix}] {issue.key}: {issue.message}")
    return "\n".join(lines)


def _require(
    issues: List[ConfigIssue],
    config_obj,
    key: str,
    message: str,
    feature: str = "core",
) -> None:
    if _is_blank(getattr(config_obj, key, None)):
        issues.append(ConfigIssue(level="error", key=key, message=message, feature=feature))


def _warn_if_missing(
    issues: List[ConfigIssue],
    config_obj,
    key: str,
    message: str,
    feature: str,
) -> None:
    if _is_blank(getattr(config_obj, key, None)):
        issues.append(ConfigIssue(level="warning", key=key, message=message, feature=feature))


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned == "" or cleaned.lower() in {"your_key_here", "sk-你的api密钥"}
    return False
