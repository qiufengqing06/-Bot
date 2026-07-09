"""Utilities for sending chat response plans with natural pacing."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, Dict, List

from nonebot_agent.agent.chat_output import ChatBubble, ChatResponsePlan
from nonebot_agent.config import config

try:
    from nonebot.log import logger
except Exception:
    logger = logging.getLogger(__name__)


SendBubbleFunc = Callable[[ChatBubble, int, int], Awaitable[None]]


class ResponseSender:
    def __init__(self) -> None:
        self._pending_followups: Dict[str, asyncio.Task] = {}

    @staticmethod
    def build_session_key(
        session_type: str,
        user_id: str,
        group_id: str | None = None,
    ) -> str:
        if session_type == "group" and group_id:
            return f"group:{group_id}"
        return f"c2c:{user_id}"

    def cancel_pending(self, session_key: str) -> None:
        task = self._pending_followups.pop(session_key, None)
        if task and not task.done():
            task.cancel()
            logger.debug(f"[Sender] Cancelled pending follow-up for {session_key}")

    def _compute_delay(self, bubble: ChatBubble) -> float:
        content_length = min(len(bubble.content.strip()), 80)
        base_ms = config.CHAT_DELAY_BASE_MS
        jitter_ms = random.randint(0, config.CHAT_DELAY_JITTER_MS)
        delay_ms = base_ms + (content_length * config.CHAT_DELAY_PER_CHAR_MS) + jitter_ms
        if bubble.optional:
            delay_ms = max(delay_ms, config.CHAT_OPTIONAL_FOLLOWUP_WINDOW_MS)
        return delay_ms / 1000.0

    async def send_plan(
        self,
        plan: ChatResponsePlan,
        session_key: str,
        send_bubble: SendBubbleFunc,
    ) -> List[ChatBubble]:
        sent: List[ChatBubble] = []
        total = len(plan.bubbles)
        if total == 0:
            return sent

        await send_bubble(plan.bubbles[0], 1, total)
        sent.append(plan.bubbles[0])

        for index, bubble in enumerate(plan.bubbles[1:], start=2):
            current_task = asyncio.current_task()
            try:
                if bubble.optional and current_task is not None:
                    self._pending_followups[session_key] = current_task
                await asyncio.sleep(self._compute_delay(bubble))
            except asyncio.CancelledError:
                logger.debug(f"[Sender] Follow-up cancelled for {session_key}")
                return sent
            finally:
                if bubble.optional and current_task is not None and self._pending_followups.get(session_key) is current_task:
                    self._pending_followups.pop(session_key, None)

            await send_bubble(bubble, index, total)
            sent.append(bubble)

        return sent


response_sender = ResponseSender()
