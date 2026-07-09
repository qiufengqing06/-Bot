"""Adapter for existing LangChain tools."""
from __future__ import annotations

from typing import Any, Dict

from nonebot_agent.skills.models import SkillContext, SkillSpec


def _schema_from_langchain_tool(tool: Any) -> Dict[str, Any]:
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is None:
        return {"type": "object", "properties": {}}
    if hasattr(args_schema, "model_json_schema"):
        return args_schema.model_json_schema()
    if hasattr(args_schema, "schema"):
        return args_schema.schema()
    return {"type": "object", "properties": {}}


def create_langchain_skill(tool: Any, source: str = "builtin") -> SkillSpec:
    """Wrap a LangChain tool as a normalized callable skill."""

    def handler(args: Dict[str, Any], context: SkillContext) -> Any:
        return tool.invoke(args)

    return SkillSpec(
        name=getattr(tool, "name", tool.__class__.__name__),
        display_name=getattr(tool, "name", tool.__class__.__name__),
        description=getattr(tool, "description", "") or "",
        adapter="langchain",
        source=source,
        parameters_schema=_schema_from_langchain_tool(tool),
        handler=handler,
    )
