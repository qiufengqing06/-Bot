"""
Memory writing heuristics.

The current bot suffered from replaying old answers because we used to store
entire user/assistant exchanges in long-term memory. This module extracts
user-centric facts and recent states instead, so retrieval focuses on facts
instead of old wording.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Optional


TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]\s*")
GROUP_PREFIX_RE = re.compile(r"^\[[^\]]+\]:\s*")
URL_RE = re.compile(r"https?://\S+")
CLAUSE_SPLIT_RE = re.compile(r"[，。！？；;]")
QUESTION_HINTS = (
    "？",
    "?",
    "吗",
    "么",
    "怎么",
    "如何",
    "为什么",
    "啥",
    "什么",
    "多少",
    "帮我",
    "请问",
    "能不能",
    "可以",
)
PREFERENCE_HINTS = (
    "我喜欢",
    "我最喜欢",
    "我爱",
    "我不喜欢",
    "我讨厌",
    "我更喜欢",
    "我比较喜欢",
    "我常用",
    "我习惯",
)
PROFILE_HINTS = (
    "我叫",
    "我是",
    "我在",
    "我来自",
    "我住在",
    "我读",
    "我学",
    "我的专业",
    "我的工作",
)
STATUS_HINTS = (
    "我最近",
    "我这段时间",
    "我正在",
    "我现在在",
    "我刚",
    "我打算",
    "我准备",
    "我计划",
    "我想要",
)


@dataclass
class MemoryCandidate:
    memory_type: str
    category: str
    text: str
    slot_key: Optional[str] = None


class MemoryWriter:
    """Extract user-centric memories from conversation input."""

    def strip_transport_prefix(self, text: str) -> str:
        text = TIMESTAMP_PREFIX_RE.sub("", text.strip())
        text = GROUP_PREFIX_RE.sub("", text)
        return text.strip()

    def normalize_text(self, text: str) -> str:
        cleaned = self.strip_transport_prefix(text)
        cleaned = URL_RE.sub("", cleaned)
        cleaned = re.sub(r"\s+", "", cleaned)
        return cleaned

    def is_question_like(self, text: str) -> bool:
        stripped = self.strip_transport_prefix(text)
        return any(hint in stripped for hint in QUESTION_HINTS)

    def build_candidates(self, user_message: str) -> List[MemoryCandidate]:
        stripped = self.strip_transport_prefix(user_message)
        normalized = self.normalize_text(stripped)

        if len(normalized) < 6:
            return []

        if stripped.startswith("/") or URL_RE.search(stripped):
            return []

        clauses = [part.strip() for part in CLAUSE_SPLIT_RE.split(stripped) if part.strip()]
        seen = set()
        candidates: List[MemoryCandidate] = []

        for clause in clauses or [stripped]:
            if "我" not in clause and "我们" not in clause:
                continue

            candidate = self._extract_fact_candidate(clause)
            if candidate is None:
                candidate = self._extract_event_candidate(clause)

            if candidate is None:
                continue

            key = (candidate.memory_type, candidate.slot_key, self.normalize_text(candidate.text))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)

        return candidates

    def _extract_fact_candidate(self, clause: str) -> Optional[MemoryCandidate]:
        if self.is_question_like(clause):
            return None

        matchers = [
            ("name", "profile", r"^我叫(?P<value>.+)$", "用户名字：{value}"),
            ("identity", "profile", r"^我是(?P<value>.+)$", "用户身份：{value}"),
            ("location", "profile", r"^我(?:在|住在|来自)(?P<value>.+)$", "用户所在地：{value}"),
            ("school", "profile", r"^我(?:在|就读于|读)(?P<value>.+(?:大学|学院|学校).*)$", "用户学校：{value}"),
            ("major", "profile", r"^(?:我的专业是|我学的是|我学)(?P<value>.+)$", "用户专业：{value}"),
            ("job", "profile", r"^(?:我的工作是|我是个|我是)(?P<value>.+(?:工程师|老师|学生|程序员|设计师|运营|开发).*)$", "用户职业：{value}"),
            ("like", "preference", r"^我(?:最)?喜欢(?P<value>.+)$", "用户喜欢：{value}"),
            ("dislike", "preference", r"^我(?:最)?不喜欢(?P<value>.+)$", "用户不喜欢：{value}"),
            ("dislike", "preference", r"^我讨厌(?P<value>.+)$", "用户讨厌：{value}"),
            ("habit", "preference", r"^我(?:常用|习惯|平时都用)(?P<value>.+)$", "用户习惯：{value}"),
        ]

        for slot_key, category, pattern, template in matchers:
            match = re.match(pattern, clause)
            if not match:
                continue
            value = self._clean_value(match.group("value"))
            if not value:
                return None
            return MemoryCandidate(
                memory_type="fact",
                category=category,
                slot_key=slot_key,
                text=template.format(value=value),
            )

        return None

    def _extract_event_candidate(self, clause: str) -> Optional[MemoryCandidate]:
        if self.is_question_like(clause):
            return None

        normalized = self.normalize_text(clause)
        if len(normalized) < 8:
            return None

        if any(hint in clause for hint in STATUS_HINTS):
            return MemoryCandidate(
                memory_type="event",
                category="status",
                text=f"用户近况：{clause}",
            )

        if "我" in clause and not clause.startswith("我是") and not clause.startswith("我叫"):
            return MemoryCandidate(
                memory_type="event",
                category="event",
                text=f"用户提到：{clause}",
            )

        return None

    def _clean_value(self, value: str) -> str:
        value = value.strip()
        value = value.strip("，。！？；; ")
        return value

    def build_candidate(self, user_message: str) -> Optional[MemoryCandidate]:
        candidates = self.build_candidates(user_message)
        return candidates[0] if candidates else None
