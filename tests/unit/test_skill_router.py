"""Tests for skill router selection."""
from __future__ import annotations

import pytest

from nonebot_agent.skills.models import SkillSpec, SkillContext
from nonebot_agent.skills.router import select_prompt_skills, format_prompt_skills


class TestSkillRouter:
    """Test skill routing and selection logic."""

    def test_select_prompt_skills_with_override(self):
        """Skill override should select the specified skill."""
        skills = [
            SkillSpec(
                name="skill_a",
                description="Skill A",
                adapter="langchain",
                instruction="Do A",
            ),
            SkillSpec(
                name="skill_b",
                description="Skill B",
                adapter="langchain",
                instruction="Do B",
            ),
        ]
        
        context = SkillContext(user_message="test", skill_override="skill_a")
        selected = select_prompt_skills(skills, context, limit=2)
        
        assert len(selected) == 1
        assert selected[0].name == "skill_a"

    def test_select_prompt_scores_by_triggers(self):
        """Skills should be scored by trigger matches."""
        skills = [
            SkillSpec(
                name="weather",
                description="Weather skill",
                adapter="langchain",
                instruction="Check weather",
                triggers=["天气", "weather"],
            ),
            SkillSpec(
                name="news",
                description="News skill",
                adapter="langchain",
                instruction="Get news",
                triggers=["新闻", "news"],
            ),
        ]
        
        context = SkillContext(user_message="今天天气怎么样")
        selected = select_prompt_skills(skills, context, limit=2)
        
        assert len(selected) > 0
        assert selected[0].name == "weather"

    def test_select_prompt_skills_respects_limit(self):
        """Selection should respect the limit parameter."""
        skills = [
            SkillSpec(
                name=f"skill_{i}",
                description=f"Skill {i}",
                adapter="langchain",
                instruction=f"Do {i}",
                triggers=[f"trigger_{i}"],
            )
            for i in range(5)
        ]
        
        context = SkillContext(user_message="trigger_0 trigger_1 trigger_2")
        selected = select_prompt_skills(skills, context, limit=2)
        
        assert len(selected) <= 2

    def test_format_prompt_skills_creates_markdown(self):
        """Format should create markdown with skill sections."""
        skills = [
            SkillSpec(
                name="test_skill",
                description="Test description",
                adapter="langchain",
                instruction="Test instruction",
            ),
        ]
        
        formatted = format_prompt_skills(skills, max_chars=1000)
        
        assert "## Active Skills" in formatted
        assert "test_skill" in formatted
        assert "Test description" in formatted
        assert "Test instruction" in formatted

    def test_format_prompt_skills_respects_max_chars(self):
        """Format should truncate when exceeding max_chars."""
        skills = [
            SkillSpec(
                name="long_skill",
                description="A" * 5000,
                adapter="langchain",
                instruction="B" * 5000,
            ),
        ]
        
        formatted = format_prompt_skills(skills, max_chars=100)
        
        assert len(formatted) <= 150  # Allow some margin for truncation marker
