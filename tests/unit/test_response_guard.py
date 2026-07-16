"""Tests for ResponseGuard similarity checking."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from nonebot_agent.memory.response_guard import ResponseGuard


class TestResponseGuard:
    """Test response novelty guard and similarity checking."""

    def test_normalize_removes_sticker_markers(self):
        """Sticker markers should be removed during normalization."""
        guard = ResponseGuard()
        
        text = "Hello [STICKER:test.png] world"
        normalized = guard._normalize(text)
        
        assert "[STICKER:test.png]" not in normalized
        assert "Hello" in normalized
        assert "world" in normalized

    def test_normalize_removes_punctuation(self):
        """Punctuation should be removed during normalization."""
        guard = ResponseGuard()
        
        text = "Hello, world! How are you?"
        normalized = guard._normalize(text)
        
        assert "," not in normalized
        assert "!" not in normalized
        assert "?" not in normalized

    def test_max_similarity_returns_zero_for_short_text(self):
        """Short text (< 8 chars) should return 0 similarity."""
        guard = ResponseGuard()
        
        similarity = guard._max_similarity("短", ["history"])
        assert similarity == 0.0

    def test_max_similarity_detects_exact_match(self):
        """Exact matches should return 1.0 similarity."""
        guard = ResponseGuard()
        
        similarity = guard._max_similarity("Hello world", ["Hello world"])
        assert similarity == 1.0

    def test_should_rewrite_detects_high_similarity(self):
        """High similarity (>= 0.70) should trigger rewrite."""
        guard = ResponseGuard()
        
        responses = ["这是一个很长的回复内容，用于测试相似度检测功能"]
        recent = ["这是一个很长的回复内容，用于测试相似度检测功能"]
        
        assert guard.should_rewrite(responses, recent)

    def test_should_rewrite_returns_false_for_low_similarity(self):
        """Low similarity should not trigger rewrite."""
        guard = ResponseGuard()
        
        responses = ["完全不同的内容"]
        recent = ["这是之前的回复，和现在的内容没有任何相似之处"]
        
        assert not guard.should_rewrite(responses, recent)

    def test_should_rewrite_returns_false_for_empty_recent(self):
        """Empty recent history should not trigger rewrite."""
        guard = ResponseGuard()
        
        responses = ["Some response"]
        recent = []
        
        assert not guard.should_rewrite(responses, recent)
