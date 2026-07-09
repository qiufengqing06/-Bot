"""
Response novelty guard.

When the agent drifts into repeating old answers verbatim, we perform a cheap
similarity check and only ask the LLM to rewrite when the new response is too
close to recent replies.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Iterable, List

from openai import OpenAI

from nonebot_agent.agent.chat_output import ChatResponsePlan
from nonebot_agent.agent.prompts import AgentMode
from nonebot_agent.config import config


STICKER_MARKER_RE = re.compile(r"^\[STICKER:[^\]]+\]$")


class ResponseGuard:
    def __init__(self) -> None:
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=config.LLM_API_KEY,
                base_url=config.LLM_API_URL,
            )
        return self._client

    @staticmethod
    def _normalize(text: str) -> str:
        text = STICKER_MARKER_RE.sub("", text.strip())
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[，。！？、,.!?~…]", "", text)
        return text

    def _max_similarity(self, candidate: str, history: Iterable[str]) -> float:
        normalized_candidate = self._normalize(candidate)
        if len(normalized_candidate) < 8:
            return 0.0

        best = 0.0
        for item in history:
            normalized_item = self._normalize(item)
            if not normalized_item:
                continue
            if normalized_item == normalized_candidate:
                return 1.0
            best = max(best, SequenceMatcher(a=normalized_candidate, b=normalized_item).ratio())
        return best

    def should_rewrite(self, responses: List[str], recent_responses: List[str]) -> bool:
        text_responses = [item for item in responses if not STICKER_MARKER_RE.match(item.strip())]
        if not text_responses or not recent_responses:
            return False

        candidate = "\n".join(text_responses)
        similarity = self._max_similarity(candidate, recent_responses[-20:])
        return similarity >= 0.70

    def detect_repeated_question(
        self, user_message: str, recent_user_messages: List[str]
    ) -> bool:
        """Check if the current question is semantically similar to a recent one."""
        if not user_message or not recent_user_messages:
            return False
        normalized_current = self._normalize(user_message)
        if len(normalized_current) < 6:
            return False
        for prev in recent_user_messages[-20:]:
            normalized_prev = self._normalize(prev)
            if not normalized_prev:
                continue
            if normalized_prev == normalized_current:
                return True
            ratio = SequenceMatcher(a=normalized_current, b=normalized_prev).ratio()
            if ratio >= 0.65:
                return True
        return False

    def rewrite_if_needed(
        self,
        responses: List[str],
        recent_responses: List[str],
        mode: AgentMode,
        user_message: str,
        recent_user_messages: List[str] | None = None,
    ) -> List[str]:
        is_repeated_question = (
            recent_user_messages
            and self.detect_repeated_question(user_message, recent_user_messages)
        )
        if not is_repeated_question and not self.should_rewrite(responses, recent_responses):
            return responses

        text_responses = [item for item in responses if not STICKER_MARKER_RE.match(item.strip())]
        sticker_responses = [item for item in responses if STICKER_MARKER_RE.match(item.strip())]
        if not text_responses:
            return responses

        client = self._get_client()
        recent_excerpt = "\n".join(f"- {item}" for item in recent_responses[-4:])

        repeated_hint = (
            "\n注意：用户又问了一遍类似的问题。请给出不同的角度、更简短的版本，或者补充上次没说到的点。"
            if is_repeated_question
            else ""
        )
        structural_hint = "不要只是换同义词，请改变句式结构、顺序、或者切入点。"

        if mode == AgentMode.CHAT:
            system_prompt = (
                "你是一个改写助手。请在不改变事实和人设的前提下，把回复改写得更自然、更新鲜，"
                "避免和最近回复重复。必须输出 JSON 字符串数组。"
            )
            user_prompt = (
                f"用户当前消息：{user_message}\n\n"
                f"原始回复：{json.dumps(text_responses, ensure_ascii=False)}\n\n"
                f"最近相似回复：\n{recent_excerpt}\n\n"
                f"要求：保留原意，不要道歉，不要解释在改写，尽量换句式和展开点。{structural_hint}{repeated_hint}"
            )
        else:
            system_prompt = (
                "你是一个改写助手。请在不改变事实和结论的前提下，把回复改写得更自然、更新鲜，"
                "避免和最近回复重复。直接输出改写后的正文。"
            )
            user_prompt = (
                f"用户当前消息：{user_message}\n\n"
                f"原始回复：{text_responses[0]}\n\n"
                f"最近相似回复：\n{recent_excerpt}\n\n"
                f"要求：保留事实，不要道歉，不要提到自己在改写，不要复述最近回复的原句。{structural_hint}{repeated_hint}"
            )

        try:
            result = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.9 if mode == AgentMode.CHAT else 0.5,
                max_tokens=400,
            )
            content = (result.choices[0].message.content or "").strip()
            if not content:
                return responses

            if mode == AgentMode.CHAT:
                rewritten = json.loads(content)
                if isinstance(rewritten, list):
                    rewritten = [item.strip() for item in rewritten if isinstance(item, str) and item.strip()]
                    if rewritten:
                        return rewritten + sticker_responses
            else:
                rewritten = content.strip()
                if rewritten:
                    return [rewritten] + sticker_responses
        except Exception:
            return responses

        return responses

    def rewrite_plan_if_needed(
        self,
        plan: ChatResponsePlan,
        recent_responses: List[str],
        mode: AgentMode,
        user_message: str,
        recent_user_messages: List[str] | None = None,
    ) -> ChatResponsePlan:
        text_responses = [bubble.content for bubble in plan.text_bubbles() if bubble.content.strip()]
        if not text_responses:
            return plan

        rewritten = self.rewrite_if_needed(
            responses=text_responses,
            recent_responses=recent_responses,
            mode=mode,
            user_message=user_message,
            recent_user_messages=recent_user_messages,
        )
        if rewritten == text_responses:
            return plan

        return plan.with_rewritten_texts(rewritten)
