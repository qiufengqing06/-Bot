"""Agent package exports with lazy imports."""
from __future__ import annotations

from importlib import import_module


__all__ = [
    "get_agent",
    "create_agent",
    "parse_chat_response",
    "parse_chat_plan",
    "AgentMode",
    "get_mode_from_message",
    "get_system_prompt_with_context",
    "CHAT_MODE_PROMPT",
    "PROFESSIONAL_MODE_PROMPT",
]

_EXPORTS = {
    "get_agent": ("nonebot_agent.agent.graph", "get_agent"),
    "create_agent": ("nonebot_agent.agent.graph", "create_agent"),
    "parse_chat_response": ("nonebot_agent.agent.graph", "parse_chat_response"),
    "parse_chat_plan": ("nonebot_agent.agent.graph", "parse_chat_plan"),
    "AgentMode": ("nonebot_agent.agent.prompts", "AgentMode"),
    "get_mode_from_message": ("nonebot_agent.agent.prompts", "get_mode_from_message"),
    "get_system_prompt_with_context": ("nonebot_agent.agent.prompts", "get_system_prompt_with_context"),
    "CHAT_MODE_PROMPT": ("nonebot_agent.agent.prompts", "CHAT_MODE_PROMPT"),
    "PROFESSIONAL_MODE_PROMPT": ("nonebot_agent.agent.prompts", "PROFESSIONAL_MODE_PROMPT"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
