"""Tests for proactive policy helpers."""
from __future__ import annotations

from datetime import datetime
import unittest

from nonebot_agent.services.proactive_service import (
    choose_topic_strategy,
    clean_online_topic_text,
    format_online_topic_candidate,
    format_proactive_topic_message,
    in_active_window,
    message_has_proactive_leak,
    seconds_until_active_window,
    split_topic_candidate,
    split_target_ids,
    topic_candidate_has_detail,
    topic_candidate_is_chatworthy,
    topic_to_plain_text,
)


class ProactivePolicyTests(unittest.TestCase):
    def test_split_target_ids_supports_multi_separator_and_dedupes(self):
        raw = "32983424, 781542；12345\n781542,abc,  999"

        result = split_target_ids(raw)

        self.assertEqual(result, ["32983424", "781542", "12345", "999"])

    def test_in_active_window_for_daytime_range(self):
        self.assertTrue(in_active_window(datetime(2026, 5, 6, 9, 0), 9, 23))
        self.assertTrue(in_active_window(datetime(2026, 5, 6, 22, 59), 9, 23))
        self.assertFalse(in_active_window(datetime(2026, 5, 6, 8, 59), 9, 23))

    def test_seconds_until_active_window_waits_until_morning(self):
        now = datetime(2026, 5, 6, 1, 30)

        seconds = seconds_until_active_window(now, 9, 23)

        self.assertEqual(seconds, int((9 - 1.5) * 3600))

    def test_choose_topic_strategy(self):
        self.assertEqual(
            choose_topic_strategy("group", True, False, 0.55, 0.1, 0.1),
            "history",
        )
        self.assertEqual(
            choose_topic_strategy("c2c", False, True, 0.55, 0.9, 0.9),
            "online",
        )
        self.assertEqual(
            choose_topic_strategy("group", True, True, 0.55, 0.9, 0.2),
            "blended",
        )

    def test_clean_online_topic_text_filters_search_artifacts(self):
        query = "今天热搜榜 有趣话题"

        self.assertEqual(clean_online_topic_text("SEARCH_ALWAYS", query), "")
        self.assertEqual(clean_online_topic_text("202605101200565dbfbcac7f8c4757", query), "")
        self.assertEqual(clean_online_topic_text(query, query), "")
        self.assertEqual(clean_online_topic_text("热搜话题：今天热搜榜 有趣话题", query), "")
        self.assertEqual(clean_online_topic_text("科技：AI 模型又更新了", query), "AI 模型又更新了")
        self.assertEqual(clean_online_topic_text("30个新颖的校园辩论赛题目", query), "")
        self.assertEqual(clean_online_topic_text("以我缤纷色彩，许你花样年华", query), "")

    def test_topic_candidate_keeps_label_for_prompt_but_plain_text_for_chat(self):
        candidate = format_online_topic_candidate("热搜", "年轻人开始反向旅游")

        self.assertEqual(candidate, "热搜：年轻人开始反向旅游")
        self.assertEqual(topic_to_plain_text(candidate), "年轻人开始反向旅游")

    def test_topic_candidate_keeps_content_detail(self):
        candidate = format_online_topic_candidate(
            "科技",
            "某公司降价30%卖大模型",
            "但要求客户必须使用稳定币结算",
        )

        self.assertEqual(
            candidate,
            "科技：某公司降价30%卖大模型｜要求客户必须使用稳定币结算",
        )
        self.assertEqual(
            split_topic_candidate(candidate),
            ("某公司降价30%卖大模型", "要求客户必须使用稳定币结算"),
        )
        self.assertTrue(topic_candidate_has_detail(candidate))

    def test_topic_candidate_rejects_promotional_campus_copy(self):
        candidate = format_online_topic_candidate(
            "校园",
            "以我缤纷色彩，许你花样年华",
            "对刚踏入大学校园的你们来说，这校园突然的大事件可能让你们来不及反应",
        )

        self.assertEqual(candidate, "")
        self.assertFalse(topic_candidate_is_chatworthy(candidate, require_detail=True))

    def test_format_proactive_topic_message_uses_content_detail(self):
        candidate = format_online_topic_candidate(
            "科技",
            "某公司降价30%卖大模型",
            "但要求客户必须使用稳定币结算",
        )

        message = format_proactive_topic_message("c2c", candidate)

        self.assertIn("某公司降价30%卖大模型", message)
        self.assertIn("稳定币", message)
        self.assertIn("食堂", message)
        self.assertNotIn("刚看到个话题", message)
        self.assertNotIn("感觉还挺有聊头", message)
        self.assertNotIn("重点好像是", message)

    def test_message_has_proactive_leak_detects_old_bad_fallback(self):
        self.assertTrue(message_has_proactive_leak("刚看到个话题 热搜话题： SEARCH_ALWAYS"))
        self.assertTrue(message_has_proactive_leak("刚看到个话题 科技话题： 202605101200565dbfbcac7f8c4757"))
        self.assertTrue(message_has_proactive_leak("刚好看到“年轻人开始反向旅游”，感觉还挺有聊头的。"))
        self.assertTrue(
            message_has_proactive_leak(
                "刚看到“以我缤纷色彩，许你花样年华”，重点好像是对刚踏入大学校园的你们来说。"
            )
        )
        self.assertFalse(
            message_has_proactive_leak(
                "刚刷到“某公司降价30%卖大模型”，说是要求客户必须使用稳定币结算。降价还绑条件，怎么有种食堂套餐打折的味道..."
            )
        )


if __name__ == "__main__":
    unittest.main()
