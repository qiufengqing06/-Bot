"""Skill prefix routing helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from nonebot_agent.config import config
from nonebot_agent.skills.models import normalize_skill_name


@dataclass
class SkillPrefixRoute:
    """A parsed skill override from a user message prefix."""

    prefix: str
    skill_name: str
    content: str
    exclusive: bool = True


def parse_prefix_aliases(raw_value: str | None = None) -> Dict[str, str]:
    """Parse aliases like ``E:ai-li-xi-ya,e:ai-li-xi-ya``."""
    raw_value = config.SKILLS_PREFIX_ALIASES if raw_value is None else raw_value
    aliases: Dict[str, str] = {}
    for item in (raw_value or "").split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        prefix, skill_name = item.split(":", 1)
        prefix = prefix.strip()
        skill_name = normalize_skill_name(skill_name.strip())
        if prefix and skill_name:
            aliases[prefix] = skill_name
    return aliases


def parse_skill_prefix(content: str, aliases: Dict[str, str] | None = None) -> Optional[SkillPrefixRoute]:
    """Return a skill route when content starts with a configured slash prefix."""
    text = (content or "").strip()
    if not text.startswith("/"):
        return None

    aliases = aliases or parse_prefix_aliases()
    for prefix in sorted(aliases, key=len, reverse=True):
        marker = "/" + prefix
        if not text.lower().startswith(marker.lower()):
            continue

        if len(text) > len(marker):
            next_char = text[len(marker)]
            if next_char.isascii() and (next_char.isalnum() or next_char in {"_", "-"}):
                continue
            remainder = text[len(marker):].lstrip()
        else:
            remainder = ""

        return SkillPrefixRoute(
            prefix=prefix,
            skill_name=aliases[prefix],
            content=remainder,
            exclusive=True,
        )
    return None
