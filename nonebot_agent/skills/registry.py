"""Skill registry for built-in and local skills."""
from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from nonebot_agent.config import config
from nonebot_agent.skills.adapters.langchain_adapter import create_langchain_skill
from nonebot_agent.skills.adapters.markdown_adapter import load_markdown_skills
from nonebot_agent.skills.adapters.script_adapter import create_script_skills
from nonebot_agent.skills.knowledge import SkillReferenceIndex, format_reference_chunks
from nonebot_agent.skills.models import SkillContext, SkillSpec, normalize_skill_name
from nonebot_agent.skills.router import format_prompt_skills, select_prompt_skills

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Load, register, and expose skills to the agent runtime."""

    def __init__(self, skills_dir: Optional[str] = None) -> None:
        self.skills_dir = Path(skills_dir or config.SKILLS_DIR)
        self.state_file = Path(config.SKILLS_STATE_FILE)
        self._skills: Dict[str, SkillSpec] = {}
        self._state: Dict[str, Dict[str, object]] = {}
        self._reference_index = SkillReferenceIndex()
        self._loaded = False

    def clear(self) -> None:
        self._skills.clear()
        self._reference_index.clear()
        self._loaded = False

    def reload(self) -> None:
        self.clear()
        self.ensure_loaded()

    def _load_state(self) -> None:
        if not self.state_file.exists():
            self._state = {}
            return
        try:
            loaded = json.loads(self.state_file.read_text(encoding="utf-8"))
            self._state = loaded if isinstance(loaded, dict) else {}
        except Exception:
            self._state = {}

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load_state()
        self.register_builtin_tools()
        if config.SKILLS_AUTO_LOAD:
            self.load_local_skills()
        self._loaded = True

    def register(self, skill: SkillSpec) -> SkillSpec:
        base_name = normalize_skill_name(skill.name)
        name = base_name
        suffix = 2
        while name in self._skills:
            name = normalize_skill_name(f"{base_name}_{suffix}")
            suffix += 1
        skill.name = name
        state = self._state.get(name, {})
        if "enabled" in state:
            skill.enabled = bool(state["enabled"])
        self._skills[name] = skill
        return skill

    def register_many(self, skills: Iterable[SkillSpec]) -> None:
        for skill in skills:
            self.register(skill)

    def register_builtin_tools(self) -> None:
        try:
            from nonebot_agent.tools import (
                read_webpage,
                search_from_internet,
                search_stickers_tool,
                send_sticker_by_url,
            )
        except Exception as exc:
            logger.warning("Failed to load built-in LangChain skills: %s", exc)
            return

        self.register_many(
            create_langchain_skill(tool)
            for tool in [
                read_webpage,
                search_from_internet,
                search_stickers_tool,
                send_sticker_by_url,
            ]
        )

    def load_local_skills(self) -> None:
        local_skills = load_markdown_skills(self.skills_dir)
        self.register_many(local_skills)
        if config.SKILLS_ALLOW_LOCAL_CODE:
            script_skills = []
            for skill in local_skills:
                script_skills.extend(create_script_skills(skill))
            self.register_many(script_skills)

    def get(self, name: str) -> Optional[SkillSpec]:
        self.ensure_loaded()
        if name in self._skills:
            return self._skills[name]
        for skill in self._skills.values():
            if name in skill.aliases:
                return skill
        return None

    def list_skills(self) -> List[SkillSpec]:
        self.ensure_loaded()
        return list(self._skills.values())

    def set_enabled(self, name: str, enabled: bool) -> bool:
        self.ensure_loaded()
        skill = self.get(name)
        if not skill:
            return False
        skill.enabled = enabled
        self._state.setdefault(skill.name, {})["enabled"] = enabled
        self._save_state()
        return True

    def list_tools(self, context: SkillContext) -> List[SkillSpec]:
        self.ensure_loaded()
        return [
            skill
            for skill in self._skills.values()
            if skill.is_tool and skill.allows_context(context)
        ]

    def get_openai_tools(self, context: SkillContext) -> List[dict]:
        if not config.SKILLS_ENABLED:
            return []

        tools = []
        for skill in self.list_tools(context):
            schema = skill.to_openai_tool()
            if schema:
                tools.append(schema)
        return tools

    def get_prompt_instructions(self, context: SkillContext) -> str:
        if not config.SKILLS_ENABLED:
            return ""

        selected = select_prompt_skills(
            self.list_skills(),
            context=context,
            limit=config.SKILLS_MAX_ACTIVE,
        )
        reference_contexts: Dict[str, str] = {}
        for skill in selected:
            snippets = self._reference_index.search(
                skill,
                query=context.user_message,
                top_k=config.SKILLS_REFERENCE_TOP_K,
            )
            reference_contexts[skill.name] = format_reference_chunks(
                snippets,
                config.SKILLS_REFERENCE_MAX_CHARS,
            )

        prompt = format_prompt_skills(
            selected,
            config.SKILLS_PROMPT_MAX_CHARS,
            reference_contexts=reference_contexts,
        )

        missing_requirements = self.get_missing_requirements(selected)
        if missing_requirements:
            prompt += (
                "\n\n## Skill Compatibility Notes\n"
                + "\n".join(
                    f"- {skill_name} declares missing dependency: {requirement}"
                    for skill_name, requirement in missing_requirements
                )
                + "\nIf the missing dependency affects behavior, approximate it using the bot's native response planner."
            )
        return prompt

    def get_missing_requirements(self, skills: Iterable[SkillSpec]) -> List[tuple[str, str]]:
        installed_names = {skill.name for skill in self.list_skills()}
        missing: List[tuple[str, str]] = []
        for skill in skills:
            for requirement in skill.requires:
                normalized = normalize_skill_name(requirement)
                if normalized not in installed_names and requirement not in installed_names:
                    missing.append((skill.name, requirement))
        return missing


_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
