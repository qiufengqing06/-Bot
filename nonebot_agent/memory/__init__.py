"""Memory package exports.

Keep imports lazy so lightweight helpers can be used without pulling in the
full LangChain/Chroma stack at package import time.
"""
from __future__ import annotations

from importlib import import_module


__all__ = [
    "MemoryManager",
    "ChromaMemory",
    "MemoryWriter",
    "MemoryDeduper",
    "StructuredMemoryStore",
    "MemorySummaryManager",
    "ResponseGuard",
]

_EXPORTS = {
    "MemoryManager": ("nonebot_agent.memory.memory_manager", "MemoryManager"),
    "ChromaMemory": ("nonebot_agent.memory.chroma_memory", "ChromaMemory"),
    "MemoryWriter": ("nonebot_agent.memory.memory_writer", "MemoryWriter"),
    "MemoryDeduper": ("nonebot_agent.memory.memory_deduper", "MemoryDeduper"),
    "StructuredMemoryStore": ("nonebot_agent.memory.memory_store", "StructuredMemoryStore"),
    "MemorySummaryManager": ("nonebot_agent.memory.memory_summary", "MemorySummaryManager"),
    "ResponseGuard": ("nonebot_agent.memory.response_guard", "ResponseGuard"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
