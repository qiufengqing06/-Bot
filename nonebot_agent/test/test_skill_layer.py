"""Tests for the skill compatibility layer."""
from __future__ import annotations

from contextlib import contextmanager
import shutil
import unittest
import os
import sys
import uuid
from pathlib import Path

import nonebot_agent.skills.registry as registry_module
from nonebot_agent.skills.adapters.markdown_adapter import load_markdown_skill
from nonebot_agent.skills.adapters.script_adapter import create_script_skills
from nonebot_agent.config import config
from nonebot_agent.skills.executor import skill_executor
from nonebot_agent.skills.models import SkillContext, SkillSpec
from nonebot_agent.skills.prefixes import parse_skill_prefix
from nonebot_agent.skills.registry import SkillRegistry
from nonebot_agent.skills.router import format_prompt_skills, select_prompt_skills


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".tmp" / "tests"


@contextmanager
def make_temp_dir():
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield str(temp_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class SkillLayerTests(unittest.TestCase):
    def test_markdown_loader_parses_frontmatter(self):
        with make_temp_dir() as tmp:
            skill_dir = Path(tmp) / "campus"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: campus_chat
display_name: Campus Chat
description: Helps with campus conversations.
triggers:
  - exam
  - dorm
modes:
  - chat
---

# Campus Chat

Talk like a classmate when campus topics appear.
""",
                encoding="utf-8",
            )

            skill = load_markdown_skill(skill_dir)

        self.assertIsNotNone(skill)
        assert skill is not None
        self.assertEqual(skill.name, "campus_chat")
        self.assertEqual(skill.display_name, "Campus Chat")
        self.assertEqual(skill.triggers, ["exam", "dorm"])
        self.assertEqual(skill.modes, ["chat"])
        self.assertIn("Talk like a classmate", skill.instruction)

    def test_router_selects_triggered_prompt_skill(self):
        triggered = SkillSpec(
            name="campus",
            display_name="Campus",
            description="Campus chat",
            adapter="markdown",
            instruction="Use campus examples.",
            triggers=["exam"],
            modes=["chat"],
        )
        fallback = SkillSpec(
            name="general",
            description="Always available fallback",
            adapter="markdown",
            instruction="General instruction.",
            modes=["chat"],
        )
        context = SkillContext(mode="chat", user_message="I have an exam tomorrow")

        selected = select_prompt_skills([fallback, triggered], context, limit=1)
        prompt = format_prompt_skills(selected, max_chars=500)

        self.assertEqual([skill.name for skill in selected], ["campus"])
        self.assertIn("Use campus examples.", prompt)
        self.assertNotIn("General instruction.", prompt)

    def test_prefix_route_supports_elysia_without_catching_long_commands(self):
        route = parse_skill_prefix(
            "/E 爱莉希雅是谁",
            aliases={"E": "ai-li-xi-ya", "e": "ai-li-xi-ya"},
        )

        self.assertIsNotNone(route)
        assert route is not None
        self.assertEqual(route.skill_name, "ai-li-xi-ya")
        self.assertEqual(route.content, "爱莉希雅是谁")
        self.assertTrue(route.exclusive)
        self.assertIsNone(
            parse_skill_prefix(
                "/emotion status",
                aliases={"E": "ai-li-xi-ya", "e": "ai-li-xi-ya"},
            )
        )

    def test_override_selects_named_skill_and_skips_fallbacks(self):
        target = SkillSpec(
            name="ai-li-xi-ya",
            description="Elysia roleplay",
            adapter="markdown",
            instruction="Use Elysia.",
            triggers=["Elysia"],
        )
        fallback = SkillSpec(
            name="general",
            description="General fallback",
            adapter="markdown",
            instruction="Use general.",
        )
        context = SkillContext(
            mode="chat",
            user_message="plain message",
            skill_override="ai-li-xi-ya",
            skill_exclusive=True,
        )

        selected = select_prompt_skills([fallback, target], context, limit=3)

        self.assertEqual([skill.name for skill in selected], ["ai-li-xi-ya"])

    def test_registry_injects_relevant_reference_snippets(self):
        with make_temp_dir() as tmp:
            skill_dir = Path(tmp) / "elysia"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: ai-li-xi-ya
description: Elysia roleplay.
---

# Elysia

Follow the role.
""",
                encoding="utf-8",
            )
            (skill_dir / "relations.md").write_text(
                "Kevin is an important companion and co-leader in this reference.",
                encoding="utf-8",
            )

            registry = SkillRegistry(skills_dir=tmp)
            registry.state_file = Path(tmp) / ".skill_state.json"
            prompt = registry.get_prompt_instructions(
                SkillContext(
                    mode="chat",
                    user_message="What is Elysia's relation with Kevin?",
                    skill_override="ai-li-xi-ya",
                    skill_exclusive=True,
                )
            )

        self.assertIn("Relevant Skill References", prompt)
        self.assertIn("Kevin is an important companion", prompt)

    def test_script_adapter_runs_only_whitelisted_safe_script(self):
        with make_temp_dir() as tmp:
            skill_dir = Path(tmp) / "skill"
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            script = scripts_dir / "nav.py"
            script.write_text(
                "import os, sys\n"
                "print('args=' + '|'.join(sys.argv[1:]))\n"
                "print('leak=' + os.environ.get('SHOULD_NOT_LEAK', ''))\n",
                encoding="utf-8",
            )
            spec = SkillSpec(
                name="demo",
                description="Demo skill.",
                adapter="markdown",
                source=str(skill_dir / "SKILL.md"),
                root_dir=str(skill_dir),
                instruction="Demo.",
            )

            old_values = (
                config.SKILLS_ALLOW_LOCAL_CODE,
                config.SKILLS_SCRIPT_ALLOWLIST,
                config.SKILLS_SCRIPT_PYTHON,
            )
            os.environ["SHOULD_NOT_LEAK"] = "secret"
            try:
                config.SKILLS_ALLOW_LOCAL_CODE = True
                config.SKILLS_SCRIPT_ALLOWLIST = "demo:scripts/nav.py"
                config.SKILLS_SCRIPT_PYTHON = sys.executable
                script_skills = create_script_skills(spec)
                output = script_skills[0].handler(
                    {"action": "search", "query": "hello"},
                    SkillContext(),
                )
                rejected = script_skills[0].handler(
                    {"action": "show", "query": "../.env"},
                    SkillContext(),
                )
            finally:
                (
                    config.SKILLS_ALLOW_LOCAL_CODE,
                    config.SKILLS_SCRIPT_ALLOWLIST,
                    config.SKILLS_SCRIPT_PYTHON,
                ) = old_values
                os.environ.pop("SHOULD_NOT_LEAK", None)

        self.assertEqual(len(script_skills), 1)
        self.assertIn("args=search|hello", output)
        self.assertIn("leak=", output)
        self.assertNotIn("secret", output)
        self.assertEqual(rejected, "Unsafe file path rejected.")

    def test_registry_exposes_callable_skill_as_openai_tool(self):
        registry = SkillRegistry(skills_dir="")
        registry._loaded = True
        registry.register(
            SkillSpec(
                name="fake tool",
                description="A fake callable skill.",
                adapter="test",
                parameters_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                handler=lambda args, context: "ok",
            )
        )

        tools = registry.get_openai_tools(SkillContext())

        self.assertEqual(tools[0]["function"]["name"], "fake_tool")
        self.assertEqual(
            tools[0]["function"]["parameters"]["properties"]["query"]["type"],
            "string",
        )

    def test_executor_invokes_registered_skill(self):
        registry = SkillRegistry(skills_dir="")
        registry._loaded = True
        registry.register(
            SkillSpec(
                name="echo",
                description="Echo input.",
                adapter="test",
                parameters_schema={"type": "object", "properties": {}},
                handler=lambda args, context: f"{context.user_id}:{args['text']}",
            )
        )

        original_registry = registry_module._registry
        registry_module._registry = registry
        try:
            result = skill_executor.invoke(
                "echo",
                {"text": "hello"},
                SkillContext(user_id="42"),
            )
        finally:
            registry_module._registry = original_registry

        self.assertTrue(result.success)
        self.assertEqual(result.content, "42:hello")


if __name__ == "__main__":
    unittest.main()
