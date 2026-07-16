"""Tests for ChatResponsePlan parsing and normalization."""
from __future__ import annotations

import pytest

from nonebot_agent.agent.chat_output import (
    ChatBubble,
    ChatResponsePlan,
    parse_chat_response_plan,
)


class TestChatResponsePlanParsing:
    """Test parsing of chat response plans from various formats."""

    def test_parse_legacy_array_keeps_primary_and_optional_followup(self):
        """Legacy array format should create primary + optional followup bubbles."""
        plan = parse_chat_response_plan('["刚回寝室", "今天满课 累死了"]')

        assert plan.reply_mode == "followup"
        assert len(plan.bubbles) == 2
        assert plan.bubbles[0].role == "primary"
        assert plan.bubbles[0].optional is False
        assert plan.bubbles[1].role == "followup"
        assert plan.bubbles[1].optional is True
        assert plan.canonical_text() == "刚回寝室"

    def test_parse_object_clamps_extra_followups(self):
        """Object format should clamp followups to configured max."""
        plan = parse_chat_response_plan(
            """
            {
              "reply_mode": "followup",
              "bubbles": [
                {"kind": "text", "content": "第一句", "role": "primary"},
                {"kind": "text", "content": "第二句", "role": "followup", "optional": true},
                {"kind": "text", "content": "第三句", "role": "followup", "optional": true}
              ]
            }
            """
        )

        assert len(plan.text_bubbles()) == 2
        assert "第三句" in plan.bubbles[1].content

    def test_parse_object_preserves_sticker_tail(self):
        """Sticker bubbles should be preserved at the end of the plan."""
        plan = parse_chat_response_plan(
            """
            {
              "reply_mode": "followup",
              "bubbles": [
                {"kind": "text", "content": "笑死", "role": "primary"},
                {"kind": "sticker", "content": "[STICKER:test.png]", "role": "sticker"}
              ]
            }
            """
        )

        assert plan.bubbles[1].kind == "sticker"
        assert plan.bubbles[1].content == "[STICKER:test.png]"

    def test_from_text_creates_single_bubble(self):
        """from_text should create a single text bubble."""
        plan = ChatResponsePlan.from_text("Hello world")
        
        assert plan.reply_mode == "single"
        assert len(plan.bubbles) == 1
        assert plan.bubbles[0].kind == "text"
        assert plan.bubbles[0].content == "Hello world"

    def test_from_text_empty_creates_silent(self):
        """Empty text should create a silent plan."""
        plan = ChatResponsePlan.from_text("")
        
        assert plan.is_silent
        assert len(plan.bubbles) == 0

    def test_is_silent_property(self):
        """is_silent should be True when reply_mode is silent or no bubbles."""
        silent_plan = ChatResponsePlan(reply_mode="silent", bubbles=[])
        assert silent_plan.is_silent
        
        empty_plan = ChatResponsePlan(reply_mode="single", bubbles=[])
        assert empty_plan.is_silent
        
        non_silent = ChatResponsePlan.from_text("Hello")
        assert not non_silent.is_silent
