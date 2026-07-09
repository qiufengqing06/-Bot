"""Adapter for strictly whitelisted local skill scripts."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from nonebot_agent.config import config
from nonebot_agent.skills.models import SkillContext, SkillSpec, normalize_skill_name


SAFE_NAV_ACTIONS = {"list", "search", "show", "category"}
SAFE_SHOW_EXTENSIONS = {".md", ".txt", ".json"}


@dataclass
class ScriptAllowlistItem:
    """A single allowed script entry."""

    skill_name: str
    script_path: str


def parse_script_allowlist(raw_value: str | None = None) -> List[ScriptAllowlistItem]:
    """Parse entries like ``ai-li-xi-ya:scripts/nav.py``."""
    raw_value = config.SKILLS_SCRIPT_ALLOWLIST if raw_value is None else raw_value
    items: List[ScriptAllowlistItem] = []
    for raw_item in (raw_value or "").split(","):
        raw_item = raw_item.strip()
        if not raw_item or ":" not in raw_item:
            continue
        skill_name, script_path = raw_item.split(":", 1)
        skill_name = normalize_skill_name(skill_name.strip())
        script_path = script_path.strip().replace("\\", "/")
        if skill_name and script_path:
            items.append(ScriptAllowlistItem(skill_name=skill_name, script_path=script_path))
    return items


def create_script_skills(skill: SkillSpec) -> List[SkillSpec]:
    """Create callable skill specs for scripts explicitly allowed for this skill."""
    if not config.SKILLS_ALLOW_LOCAL_CODE:
        return []
    if not skill.root_dir:
        return []

    root_dir = Path(skill.root_dir).resolve()
    script_specs: List[SkillSpec] = []
    for item in parse_script_allowlist():
        if item.skill_name != skill.name:
            continue
        script_path = (root_dir / item.script_path).resolve()
        if not _is_inside(script_path, root_dir):
            continue
        if not script_path.exists() or script_path.suffix.lower() != ".py":
            continue

        script_name = normalize_skill_name(f"{skill.name}_{script_path.stem}")
        script_specs.append(
            SkillSpec(
                name=script_name,
                display_name=f"{skill.display_name or skill.name} script: {script_path.stem}",
                description=(
                    f"Run the whitelisted local script {item.script_path} for skill {skill.name}. "
                    "Use it only for read-only file navigation/search inside this skill."
                ),
                adapter="script",
                source=str(script_path),
                root_dir=str(root_dir),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": sorted(SAFE_NAV_ACTIONS),
                            "description": "Script action to run.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Keyword, category, or safe relative file path.",
                        },
                    },
                    "required": ["action"],
                },
                permissions=["local.exec", "filesystem.read"],
                modes=skill.modes,
                session_types=skill.session_types,
                enabled=skill.enabled,
                risk_level="high",
                handler=_build_script_handler(root_dir, script_path),
            )
        )
    return script_specs


def _build_script_handler(root_dir: Path, script_path: Path):
    def handler(args: Dict[str, Any], context: SkillContext) -> str:
        action = str(args.get("action", "")).strip()
        query = str(args.get("query", "")).strip()
        if action not in SAFE_NAV_ACTIONS:
            return f"Script action is not allowed: {action}"
        if action in {"search", "show", "category"} and not query:
            return f"Script action '{action}' requires query."
        if action == "show" and not _is_safe_relative_reference(root_dir, query):
            return "Unsafe file path rejected."

        command = [config.SKILLS_SCRIPT_PYTHON, str(script_path), action]
        if query:
            command.append(query[:300])

        try:
            result = subprocess.run(
                command,
                cwd=str(root_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.SKILLS_SCRIPT_TIMEOUT_SECONDS,
                shell=False,
                stdin=subprocess.DEVNULL,
                env=_safe_env(),
            )
        except subprocess.TimeoutExpired:
            return f"Script timed out after {config.SKILLS_SCRIPT_TIMEOUT_SECONDS}s."
        except Exception as exc:
            return f"Script execution error: {exc}"

        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()
        if result.returncode != 0:
            output = "\n".join(part for part in [output, error] if part)
            output = output or f"Script exited with code {result.returncode}."

        if not output:
            output = "(script produced no output)"

        max_chars = max(1000, config.SKILLS_SCRIPT_MAX_OUTPUT_CHARS)
        if len(output) > max_chars:
            output = output[:max_chars].rstrip() + "\n...[script output truncated]"
        return output

    return handler


def _safe_env() -> Dict[str, str]:
    allowed_keys = ["PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"]
    env = {key: os.environ[key] for key in allowed_keys if key in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _is_safe_relative_reference(root_dir: Path, query: str) -> bool:
    if not query or "\x00" in query:
        return False
    candidate = Path(query)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    resolved = (root_dir / candidate).resolve()
    if not _is_inside(resolved, root_dir):
        return False
    return resolved.suffix.lower() in SAFE_SHOW_EXTENSIONS


def _is_inside(path: Path, root_dir: Path) -> bool:
    try:
        path.relative_to(root_dir)
        return True
    except ValueError:
        return False
