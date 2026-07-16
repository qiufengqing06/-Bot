"""Structured chat output plan and parsing helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Iterable, List, Optional

from nonebot_agent.config import config


STICKER_MARKER_RE = re.compile(r"^\[STICKER:[^\]]+\]$")


@dataclass
class ChatBubble:
    """A single outgoing chat bubble."""

    kind: str
    content: str
    role: str = "primary"
    optional: bool = False

    def stripped(self) -> str:
        return self.content.strip()


@dataclass
class ChatResponsePlan:
    """Normalized chat response plan."""

    reply_mode: str = "single"
    bubbles: List[ChatBubble] = field(default_factory=list)

    @property
    def is_silent(self) -> bool:
        """True when the bot chose not to respond (no bubbles to send)."""
        if self.reply_mode == "silent":
            return True
        return len(self.bubbles) == 0

    @classmethod
    def from_text(cls, text: str) -> "ChatResponsePlan":
        cleaned = text.strip()
        if not cleaned:
            # Empty/whitespace response → silent (bot chose not to speak)
            return cls(reply_mode="silent", bubbles=[])
        return cls(
            reply_mode="single",
            bubbles=[ChatBubble(kind=_detect_bubble_kind(cleaned), content=cleaned, role="primary")],
        )

    @classmethod
    def from_legacy_messages(cls, messages: Iterable[str]) -> "ChatResponsePlan":
        bubbles = []
        for index, item in enumerate(messages):
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned:
                continue
            kind = _detect_bubble_kind(cleaned)
            role = "primary" if not bubbles else ("sticker" if kind == "sticker" else "followup")
            optional = bool(bubbles and kind == "text")
            bubbles.append(ChatBubble(kind=kind, content=cleaned, role=role, optional=optional))

        if not bubbles:
            return cls(reply_mode="silent", bubbles=[])

        reply_mode = "followup" if sum(1 for bubble in bubbles if bubble.kind == "text") > 1 else "single"
        return cls(reply_mode=reply_mode, bubbles=bubbles)

    def text_bubbles(self) -> List[ChatBubble]:
        return [bubble for bubble in self.bubbles if bubble.kind == "text"]

    def primary_text(self) -> str:
        for bubble in self.text_bubbles():
            return bubble.stripped()
        return ""

    def canonical_text(self) -> str:
        required = [
            bubble.stripped()
            for bubble in self.text_bubbles()
            if bubble.stripped() and (bubble.role == "primary" or not bubble.optional)
        ]
        if required:
            return "\n".join(required)

        fallback = [bubble.stripped() for bubble in self.text_bubbles() if bubble.stripped()]
        return fallback[0] if fallback else ""

    def append_stickers(self, stickers: Iterable[str]) -> "ChatResponsePlan":
        existing = {bubble.content for bubble in self.bubbles if bubble.kind == "sticker"}
        bubbles = list(self.bubbles)
        for marker in stickers:
            cleaned = marker.strip()
            if not cleaned or cleaned in existing:
                continue
            role = "sticker" if bubbles else "primary"
            bubbles.append(
                ChatBubble(
                    kind="sticker",
                    content=cleaned,
                    role=role,
                    optional=bool(bubbles),
                )
            )
            existing.add(cleaned)
        return normalize_chat_response_plan(ChatResponsePlan(reply_mode=self.reply_mode, bubbles=bubbles))

    def with_rewritten_texts(self, texts: List[str]) -> "ChatResponsePlan":
        cleaned_texts = [item.strip() for item in texts if isinstance(item, str) and item.strip()]
        if not cleaned_texts:
            return self

        new_bubbles: List[ChatBubble] = []
        original_texts = self.text_bubbles()
        for index, content in enumerate(cleaned_texts):
            template = original_texts[index] if index < len(original_texts) else None
            new_bubbles.append(
                ChatBubble(
                    kind="text",
                    content=content,
                    role="primary" if index == 0 else "followup",
                    optional=False if index == 0 else (template.optional if template else True),
                )
            )

        for bubble in self.bubbles:
            if bubble.kind == "sticker":
                new_bubbles.append(bubble)

        reply_mode = "followup" if len(cleaned_texts) > 1 else "single"
        return normalize_chat_response_plan(ChatResponsePlan(reply_mode=reply_mode, bubbles=new_bubbles))


def parse_chat_response_plan(content: str, max_followups: Optional[int] = None) -> ChatResponsePlan:
    """Parse model output into a normalized chat response plan."""
    payload = _extract_json_payload(content)
    if isinstance(payload, dict):
        plan = _plan_from_dict(payload)
    elif isinstance(payload, list):
        plan = ChatResponsePlan.from_legacy_messages(payload)
    else:
        plan = _fallback_plan_from_text(content)
    return normalize_chat_response_plan(plan, max_followups=max_followups)


def normalize_chat_response_plan(
    plan: ChatResponsePlan,
    max_followups: Optional[int] = None,
) -> ChatResponsePlan:
    """Clamp bubble count and enforce primary/follow-up semantics."""
    max_messages = max(1, config.CHAT_MODE_MAX_MESSAGES)
    resolved_followups: int = (
        max(0, max_followups)
        if max_followups is not None
        else max(0, int(getattr(config, "CHAT_MAX_FOLLOWUPS", 1) or 0))
    )
    max_followups = resolved_followups
    normalized: List[ChatBubble] = []
    text_count = 0
    sticker_seen = set()

    for bubble in plan.bubbles:
        cleaned = bubble.stripped()
        if not cleaned:
            continue

        kind = _detect_bubble_kind(cleaned if bubble.kind != "sticker" else cleaned)
        if kind == "sticker":
            if cleaned in sticker_seen or len(normalized) >= max_messages:
                continue
            sticker_seen.add(cleaned)
            normalized.append(
                ChatBubble(
                    kind="sticker",
                    content=cleaned,
                    role="primary" if not normalized else "sticker",
                    optional=bool(normalized),
                )
            )
            continue

        if text_count == 0:
            normalized.append(ChatBubble(kind="text", content=cleaned, role="primary", optional=False))
            text_count += 1
            continue

        if text_count > max_followups or len(normalized) >= max_messages:
            last_text_index = next(
                (index for index in range(len(normalized) - 1, -1, -1) if normalized[index].kind == "text"),
                None,
            )
            if last_text_index is not None:
                merged = normalized[last_text_index].content.rstrip() + "\n" + cleaned
                last = normalized[last_text_index]
                normalized[last_text_index] = ChatBubble(
                    kind="text",
                    content=merged,
                    role=last.role,
                    optional=last.optional,
                )
            continue

        normalized.append(ChatBubble(kind="text", content=cleaned, role="followup", optional=True))
        text_count += 1

    if not normalized:
        return ChatResponsePlan(reply_mode="silent", bubbles=[])

    reply_mode = "followup" if sum(1 for bubble in normalized if bubble.kind == "text") > 1 else "single"
    return ChatResponsePlan(reply_mode=reply_mode, bubbles=normalized)


def _plan_from_dict(payload: dict[str, Any]) -> ChatResponsePlan:
    reply_mode = str(payload.get("reply_mode", "single")).strip() or "single"
    raw_bubbles = payload.get("bubbles", [])
    if not isinstance(raw_bubbles, list):
        raw_bubbles = []

    bubbles: List[ChatBubble] = []
    for index, item in enumerate(raw_bubbles):
        bubble = _bubble_from_item(item, index)
        if bubble is not None:
            bubbles.append(bubble)

    # If bubbles array is empty, check for reply_mode="silent" or fallback to silent
    if not bubbles:
        if reply_mode == "silent":
            return ChatResponsePlan(reply_mode="silent", bubbles=[])
        # Check for content/reply fields as fallback
        fallback = payload.get("content") or payload.get("reply") or ""
        fallback = str(fallback).strip()
        if not fallback:
            return ChatResponsePlan(reply_mode="silent", bubbles=[])
        return ChatResponsePlan.from_text(fallback)

    return ChatResponsePlan(reply_mode=reply_mode, bubbles=bubbles)


def _bubble_from_item(item: Any, index: int) -> ChatBubble | None:
    if isinstance(item, str):
        cleaned = item.strip()
        if not cleaned:
            return None
        kind = _detect_bubble_kind(cleaned)
        role = "primary" if index == 0 else ("sticker" if kind == "sticker" else "followup")
        return ChatBubble(kind=kind, content=cleaned, role=role, optional=index > 0 and kind == "text")

    if not isinstance(item, dict):
        return None

    content = str(item.get("content", "")).strip()
    if not content:
        return None

    kind = str(item.get("kind", _detect_bubble_kind(content))).strip() or "text"
    kind = _detect_bubble_kind(content) if kind not in {"text", "sticker"} else kind
    role = str(item.get("role", "primary" if index == 0 else "followup")).strip() or "followup"
    optional = bool(item.get("optional", index > 0 and kind == "text"))
    return ChatBubble(kind=kind, content=content, role=role, optional=optional)


def _fallback_plan_from_text(content: str) -> ChatResponsePlan:
    stripped = _strip_code_fence(content).strip()
    if "\n" in stripped:
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        filtered = [line for line in lines if not line.startswith("```")]
        if filtered:
            return ChatResponsePlan.from_legacy_messages(filtered)
    return ChatResponsePlan.from_text(stripped or content)


def _extract_json_payload(content: str) -> Any:
    candidates = []
    stripped = _strip_code_fence(content).strip()
    if stripped:
        candidates.append(stripped)

    brace_start = stripped.find("{")
    brace_end = stripped.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidates.append(stripped[brace_start:brace_end + 1])

    bracket_start = stripped.find("[")
    bracket_end = stripped.rfind("]")
    if bracket_start != -1 and bracket_end > bracket_start:
        candidates.append(stripped[bracket_start:bracket_end + 1])

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        inner = stripped[3:-3].strip()
        if inner.startswith("json"):
            inner = inner[4:].strip()
        return inner
    return content


def _detect_bubble_kind(content: str) -> str:
    return "sticker" if STICKER_MARKER_RE.match(content.strip()) else "text"
