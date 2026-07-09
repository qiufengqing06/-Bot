"""Tests for structured chat output parsing."""
from __future__ import annotations

import unittest

from nonebot_agent.agent.chat_output import parse_chat_response_plan


class ChatOutputTests(unittest.TestCase):
    def test_parse_legacy_array_keeps_primary_and_optional_followup(self):
        plan = parse_chat_response_plan('["刚回寝室", "今天满课 累死了"]')

        self.assertEqual(plan.reply_mode, "followup")
        self.assertEqual(len(plan.bubbles), 2)
        self.assertEqual(plan.bubbles[0].role, "primary")
        self.assertFalse(plan.bubbles[0].optional)
        self.assertEqual(plan.bubbles[1].role, "followup")
        self.assertTrue(plan.bubbles[1].optional)
        self.assertEqual(plan.canonical_text(), "刚回寝室")

    def test_parse_object_clamps_extra_followups(self):
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

        self.assertEqual(len(plan.text_bubbles()), 2)
        self.assertIn("第三句", plan.bubbles[1].content)

    def test_parse_object_preserves_sticker_tail(self):
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

        self.assertEqual(plan.bubbles[1].kind, "sticker")
        self.assertEqual(plan.bubbles[1].content, "[STICKER:test.png]")


if __name__ == "__main__":
    unittest.main()
