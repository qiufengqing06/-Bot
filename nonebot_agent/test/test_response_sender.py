"""Tests for natural chat response sending."""
from __future__ import annotations

import asyncio
import unittest

from nonebot_agent.agent.chat_output import ChatBubble, ChatResponsePlan
from nonebot_agent.config import config
from nonebot_agent.services.response_sender import ResponseSender


class ResponseSenderTests(unittest.TestCase):
    def setUp(self):
        self._old_values = (
            config.CHAT_DELAY_BASE_MS,
            config.CHAT_DELAY_PER_CHAR_MS,
            config.CHAT_DELAY_JITTER_MS,
            config.CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS,
        )
        config.CHAT_DELAY_BASE_MS = 0
        config.CHAT_DELAY_PER_CHAR_MS = 0
        config.CHAT_DELAY_JITTER_MS = 0
        config.CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS = 50

    def tearDown(self):
        (
            config.CHAT_DELAY_BASE_MS,
            config.CHAT_DELAY_PER_CHAR_MS,
            config.CHAT_DELAY_JITTER_MS,
            config.CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS,
        ) = self._old_values

    def test_cancel_pending_followup_stops_second_bubble(self):
        asyncio.run(self._test_cancel_pending_followup_stops_second_bubble())

    async def _test_cancel_pending_followup_stops_second_bubble(self):
        sender = ResponseSender()
        sent = []
        plan = ChatResponsePlan(
            reply_mode="followup",
            bubbles=[
                ChatBubble(kind="text", content="第一句", role="primary", optional=False),
                ChatBubble(kind="text", content="第二句", role="followup", optional=True),
            ],
        )

        async def send_bubble(bubble, index, total):
            sent.append((index, bubble.content))

        task = asyncio.create_task(sender.send_plan(plan, "c2c:10001", send_bubble))
        await asyncio.sleep(0.01)
        sender.cancel_pending("c2c:10001")
        await task

        self.assertEqual(sent, [(1, "第一句")])

    def test_followup_is_sent_when_not_cancelled(self):
        asyncio.run(self._test_followup_is_sent_when_not_cancelled())

    async def _test_followup_is_sent_when_not_cancelled(self):
        sender = ResponseSender()
        sent = []
        plan = ChatResponsePlan(
            reply_mode="followup",
            bubbles=[
                ChatBubble(kind="text", content="第一句", role="primary", optional=False),
                ChatBubble(kind="text", content="第二句", role="followup", optional=True),
            ],
        )

        async def send_bubble(bubble, index, total):
            sent.append((index, bubble.content))

        await sender.send_plan(plan, "c2c:10002", send_bubble)

        self.assertEqual(sent, [(1, "第一句"), (2, "第二句")])


if __name__ == "__main__":
    unittest.main()
