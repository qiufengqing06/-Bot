"""Tests for MemoryWriter extraction logic."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from nonebot_agent.memory.memory_writer import MemoryWriter


class TestMemoryWriter:
    """Test memory extraction from user messages."""

    def test_strip_transport_prefix_removes_timestamps(self):
        """Transport prefixes (timestamps, group names) should be stripped."""
        writer = MemoryWriter()
        
        text = "[2024-01-01 12:00] 你好"
        result = writer.strip_transport_prefix(text)
        assert result == "你好"
        
        text = "[群聊]: 大家好"
        result = writer.strip_transport_prefix(text)
        assert result == "大家好"

    def test_normalize_text_removes_urls_and_whitespace(self):
        """Normalization should remove URLs and collapse whitespace."""
        writer = MemoryWriter()
        
        text = "我喜欢 https://example.com 这个网站"
        result = writer.normalize_text(text)
        assert "https" not in result
        assert "我喜欢" in result

    def test_is_question_like_detects_questions(self):
        """Question detection should identify various question patterns."""
        writer = MemoryWriter()
        
        assert writer.is_question_like("这是什么？")
        assert writer.is_question_like("怎么办")
        assert writer.is_question_like("帮我看看")
        assert not writer.is_question_like("我喜欢这个")

    def test_build_candidates_extracts_profile_info(self):
        """Profile information should be extracted via regex fallback."""
        writer = MemoryWriter()
        
        candidates = writer._build_candidates_regex("我叫小明", writer.normalize_text("我叫小明"))
        assert len(candidates) > 0
        assert candidates[0].category == "profile"
        assert "小明" in candidates[0].text

    def test_build_candidates_extracts_preferences(self):
        """Preference information should be extracted via regex fallback."""
        writer = MemoryWriter()
        
        candidates = writer._build_candidates_regex("我喜欢喝咖啡", writer.normalize_text("我喜欢喝咖啡"))
        assert len(candidates) > 0
        assert candidates[0].category == "preference"
        assert "咖啡" in candidates[0].text
