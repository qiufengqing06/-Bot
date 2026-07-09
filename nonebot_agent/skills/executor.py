"""Unified skill execution entry point."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Dict

from nonebot_agent.config import config
from nonebot_agent.skills.models import SkillContext, SkillResult
from nonebot_agent.skills.registry import get_skill_registry


class SkillExecutor:
    """Execute callable skills with consistent error handling."""

    def invoke(self, name: str, args: Dict[str, Any], context: SkillContext) -> SkillResult:
        registry = get_skill_registry()
        skill = registry.get(name)
        if not skill:
            return SkillResult(content=f"Skill not found: {name}", success=False, error="not_found")
        if not skill.allows_context(context):
            return SkillResult(
                content=f"Skill is not allowed in this context: {name}",
                success=False,
                error="not_allowed",
            )
        if not skill.handler:
            return SkillResult(
                content=f"Skill is prompt-only and cannot be called as a tool: {name}",
                success=False,
                error="not_callable",
            )

        pool = None
        future = None
        try:
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(skill.handler, args or {}, context)
            output = future.result(timeout=config.SKILLS_TOOL_TIMEOUT_SECONDS)
            pool.shutdown(wait=False)
            return SkillResult(content=str(output), success=True)
        except TimeoutError:
            if future:
                future.cancel()
            if pool:
                pool.shutdown(wait=False)
            return SkillResult(
                content=f"Skill execution timed out: {name}",
                success=False,
                error="timeout",
            )
        except Exception as exc:
            if pool:
                pool.shutdown(wait=False)
            return SkillResult(
                content=f"Skill execution error: {exc}",
                success=False,
                error=str(exc),
            )


skill_executor = SkillExecutor()
