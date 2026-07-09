"""Skill compatibility layer."""
from nonebot_agent.skills.executor import SkillExecutor, skill_executor
from nonebot_agent.skills.models import SkillContext, SkillResult, SkillSpec
from nonebot_agent.skills.prefixes import SkillPrefixRoute, parse_skill_prefix
from nonebot_agent.skills.registry import SkillRegistry, get_skill_registry

__all__ = [
    "SkillContext",
    "SkillExecutor",
    "SkillPrefixRoute",
    "SkillRegistry",
    "SkillResult",
    "SkillSpec",
    "get_skill_registry",
    "parse_skill_prefix",
    "skill_executor",
]
