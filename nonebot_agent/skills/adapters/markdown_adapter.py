"""Loader for local SKILL.md prompt skills."""
from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from nonebot_agent.skills.models import SkillSpec, normalize_skill_name


LIST_KEYS = {"aliases", "requires", "triggers", "permissions", "modes", "session_types"}


def _coerce_value(value: str):
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",")]
    return value.strip("'\"")


def parse_simple_yaml(text: str) -> Dict[str, object]:
    """Parse the small YAML subset used by local skill manifests."""
    data: Dict[str, object] = {}
    current_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("-") and current_key:
            item = stripped[1:].strip().strip("'\"")
            if item:
                data.setdefault(current_key, [])
                current_list = data[current_key]
                if isinstance(current_list, list):
                    current_list.append(item)
            continue

        if ":" not in stripped:
            current_key = None
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key if key in LIST_KEYS and not value else None
        if not value and key in LIST_KEYS:
            data[key] = []
        else:
            data[key] = _coerce_value(value)

    return data


def split_frontmatter(markdown: str) -> Tuple[Dict[str, object], str]:
    """Split optional YAML frontmatter from SKILL.md."""
    if markdown.startswith("---"):
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", markdown, re.S)
        if match:
            return parse_simple_yaml(match.group(1)), match.group(2).strip()
    return {}, markdown.strip()


def _list_value(value: object, default: Iterable[str]) -> List[str]:
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，;\s]+", value) if item.strip()]
    return list(default)


def _metadata_from_skill_dir(skill_dir: Path) -> Dict[str, object]:
    metadata: Dict[str, object] = {}
    json_manifest = skill_dir / "manifest.json"
    if json_manifest.exists():
        try:
            loaded = json.loads(json_manifest.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                metadata.update(loaded)
        except Exception:
            pass

    manifest = skill_dir / "skill.yaml"
    if manifest.exists():
        metadata.update(parse_simple_yaml(manifest.read_text(encoding="utf-8")))
    return metadata


def load_markdown_skill(skill_dir: Path) -> SkillSpec | None:
    """Load a prompt-only skill from a directory containing SKILL.md."""
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    frontmatter, body = split_frontmatter(skill_file.read_text(encoding="utf-8"))
    metadata = _metadata_from_skill_dir(skill_dir)
    metadata.update(frontmatter)

    description = str(metadata.get("description") or "").strip()
    if not description:
        first_line = next((line.strip("# ").strip() for line in body.splitlines() if line.strip()), "")
        description = first_line or f"Local skill from {skill_dir.name}"

    return SkillSpec(
        name=normalize_skill_name(str(metadata.get("name") or skill_dir.name)),
        display_name=str(metadata.get("display_name") or metadata.get("name") or skill_dir.name),
        description=description,
        adapter="markdown",
        source=str(skill_file),
        root_dir=str(skill_dir),
        instruction=body,
        aliases=_list_value(metadata.get("aliases"), []),
        requires=_list_value(metadata.get("requires"), []),
        triggers=_list_value(metadata.get("triggers"), []),
        permissions=_list_value(metadata.get("permissions"), []),
        modes=_list_value(metadata.get("modes"), ["chat", "professional"]),
        session_types=_list_value(metadata.get("session_types"), ["c2c", "group"]),
        enabled=bool(metadata.get("enabled", True)),
        risk_level=str(metadata.get("risk_level") or "low"),
    )


def load_markdown_skills(skills_dir: Path) -> List[SkillSpec]:
    """Load all prompt-only skills under the configured skill directory."""
    if not skills_dir.exists():
        return []

    skills: List[SkillSpec] = []
    for child in sorted(skills_dir.iterdir(), key=lambda item: item.name.lower()):
        if child.is_dir():
            skill = load_markdown_skill(child)
            if skill:
                skills.append(skill)
    return skills
