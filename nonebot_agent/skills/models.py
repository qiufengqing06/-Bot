"""Shared models for the skill compatibility layer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


SkillHandler = Callable[[Dict[str, Any], "SkillContext"], Any]


def normalize_skill_name(name: str, fallback: str = "skill") -> str:
    """Normalize external skill names into OpenAI-compatible tool names."""
    raw_name = (name or fallback).strip()
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw_name)
    normalized = normalized.strip("_-")
    return (normalized or fallback)[:64]


@dataclass
class SkillContext:
    """Runtime context passed to skill execution and routing."""

    user_id: str = ""
    session_type: str = "c2c"
    group_id: Optional[str] = None
    mode: str = "professional"
    current_user_nickname: Optional[str] = None
    user_message: str = ""
    skill_override: Optional[str] = None
    skill_exclusive: bool = False


@dataclass
class SkillSpec:
    """A normalized skill definition from any supported source."""

    name: str
    description: str
    adapter: str
    display_name: Optional[str] = None
    source: str = "builtin"
    root_dir: str = ""
    parameters_schema: Dict[str, Any] = field(default_factory=dict)
    instruction: str = ""
    aliases: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    modes: List[str] = field(default_factory=lambda: ["chat", "professional"])
    session_types: List[str] = field(default_factory=lambda: ["c2c", "group"])
    enabled: bool = True
    risk_level: str = "low"
    handler: Optional[SkillHandler] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.name = normalize_skill_name(self.name)
        self.display_name = self.display_name or self.name
        self.aliases = [item.strip() for item in self.aliases if item and item.strip()]
        self.requires = [item.strip() for item in self.requires if item and item.strip()]
        self.triggers = [item.strip() for item in self.triggers if item and item.strip()]
        self.permissions = [item.strip() for item in self.permissions if item and item.strip()]
        self.modes = [item.strip() for item in self.modes if item and item.strip()]
        self.session_types = [
            item.strip() for item in self.session_types if item and item.strip()
        ]

    @property
    def is_tool(self) -> bool:
        return self.handler is not None

    @property
    def is_prompt_skill(self) -> bool:
        return bool(self.instruction.strip())

    def allows_context(self, context: SkillContext) -> bool:
        if not self.enabled:
            return False
        if self.modes and context.mode not in self.modes:
            return False
        if self.session_types and context.session_type not in self.session_types:
            return False
        return True

    def to_openai_tool(self) -> Optional[Dict[str, Any]]:
        """Convert callable skills into OpenAI function-calling schema."""
        if not self.is_tool:
            return None

        parameters = self.parameters_schema or {"type": "object", "properties": {}}
        if "type" not in parameters:
            parameters = {"type": "object", "properties": parameters}

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


@dataclass
class SkillResult:
    """Normalized skill execution result."""

    content: str
    success: bool = True
    error: Optional[str] = None
