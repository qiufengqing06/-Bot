"""Tests for skill prefix parsing."""
from __future__ import annotations

import pytest

from nonebot_agent.skills.prefixes import parse_prefix_aliases, parse_skill_prefix, SkillPrefixRoute


class TestSkillPrefixes:
    """Test skill prefix routing and parsing."""

    def test_parse_prefix_aliases_parses_format(self):
        """Prefix aliases should be parsed from 'prefix:skill_name' format."""
        aliases = parse_prefix_aliases("E:ai-li-xi-ya,e:ai-li-xi-ya")
        
        assert "E" in aliases
        assert aliases["E"] == "ai-li-xi-ya"  # normalized (hyphens preserved)
        assert "e" in aliases
        assert aliases["e"] == "ai-li-xi-ya"

    def test_parse_prefix_aliases_handles_empty_string(self):
        """Empty string should return empty dict."""
        aliases = parse_prefix_aliases("")
        assert aliases == {}

    def test_parse_skill_prefix_matches_slash_prefix(self):
        """Slash-prefixed messages should match configured aliases."""
        aliases = {"E": "ai_li_xi_ya"}
        
        route = parse_skill_prefix("/E 你好", aliases)
        
        assert route is not None
        assert route.prefix == "E"
        assert route.skill_name == "ai_li_xi_ya"
        assert route.content == "你好"

    def test_parse_skill_prefix_returns_none_for_no_match(self):
        """Non-matching prefixes should return None."""
        aliases = {"E": "ai_li_xi_ya"}
        
        route = parse_skill_prefix("/X 你好", aliases)
        assert route is None

    def test_parse_skill_prefix_returns_none_for_no_slash(self):
        """Messages without leading slash should return None."""
        aliases = {"E": "ai_li_xi_ya"}
        
        route = parse_skill_prefix("E 你好", aliases)
        assert route is None

    def test_parse_skill_prefix_handles_empty_content(self):
        """Prefix with no content should have empty content field."""
        aliases = {"E": "ai_li_xi_ya"}
        
        route = parse_skill_prefix("/E", aliases)
        
        assert route is not None
        assert route.content == ""
