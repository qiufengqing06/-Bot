"""Skill routing and prompt formatting."""
from __future__ import annotations

from typing import Dict, Iterable, List

from nonebot_agent.skills.models import SkillContext, SkillSpec


def _score_skill(skill: SkillSpec, user_message: str) -> int:
    message = (user_message or "").lower()
    if not message:
        return 0

    score = 0
    for trigger in skill.triggers:
        if trigger.lower() in message:
            score += 10

    searchable = " ".join(
        item
        for item in [skill.name, skill.display_name or "", skill.description]
        if item
    ).lower()
    for token in set(message.split()):
        if len(token) >= 2 and token in searchable:
            score += 1
    return score


def select_prompt_skills(
    skills: Iterable[SkillSpec],
    context: SkillContext,
    limit: int,
) -> List[SkillSpec]:
    """Select prompt skills relevant to the current user message."""
    if context.skill_override:
        wanted = context.skill_override
        for skill in skills:
            names = {skill.name, *(skill.aliases or [])}
            if wanted in names and skill.is_prompt_skill and skill.allows_context(context):
                return [skill]
        return []

    scored: List[tuple[int, SkillSpec]] = []
    fallback: List[SkillSpec] = []

    for skill in skills:
        if not skill.is_prompt_skill or not skill.allows_context(context):
            continue
        if not skill.triggers:
            fallback.append(skill)
            continue
        score = _score_skill(skill, context.user_message)
        if score > 0:
            scored.append((score, skill))

    scored.sort(key=lambda item: (-item[0], item[1].name))
    selected = [skill for _, skill in scored]

    remaining = max(limit - len(selected), 0)
    if remaining:
        selected.extend(fallback[:remaining])

    return selected[:limit]


def format_prompt_skills(
    skills: Iterable[SkillSpec],
    max_chars: int,
    reference_contexts: Dict[str, str] | None = None,
) -> str:
    """Format selected prompt skills into a compact system-prompt section."""
    reference_contexts = reference_contexts or {}
    sections: List[str] = []
    for skill in skills:
        title = skill.display_name or skill.name
        references = reference_contexts.get(skill.name, "").strip()
        section = (
            f"### {title} ({skill.name})\n"
            f"{skill.description}\n\n"
            f"{skill.instruction.strip()}"
        ).strip()
        if references:
            section += f"\n\n#### Relevant Skill References\n{references}"
        sections.append(section)

    if not sections:
        return ""

    prompt = "## Active Skills\n" + "\n\n".join(sections)
    if max_chars > 0 and len(prompt) > max_chars:
        return prompt[:max_chars].rstrip() + "\n...[skill instructions truncated]"
    return prompt
