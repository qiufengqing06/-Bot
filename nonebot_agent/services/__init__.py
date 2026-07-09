"""Service package exports with lazy imports."""
from __future__ import annotations

from importlib import import_module


__all__ = ["generate_response", "memory_manager", "response_sender"]

_EXPORTS = {
    "generate_response": ("nonebot_agent.services.chat_service", "generate_response"),
    "memory_manager": ("nonebot_agent.services.chat_service", "memory_manager"),
    "response_sender": ("nonebot_agent.services.response_sender", "response_sender"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
