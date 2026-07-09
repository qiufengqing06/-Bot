"""
Text normalization and fuzzy dedupe helpers for structured memories.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher


PUNCT_RE = re.compile(r"[，。！？、；：,.!?;:\-\s]+")


class MemoryDeduper:
    def normalize(self, text: str) -> str:
        text = text.strip().lower()
        text = PUNCT_RE.sub("", text)
        return text

    def similarity(self, left: str, right: str) -> float:
        left_norm = self.normalize(left)
        right_norm = self.normalize(right)
        if not left_norm or not right_norm:
            return 0.0
        if left_norm == right_norm:
            return 1.0
        return SequenceMatcher(a=left_norm, b=right_norm).ratio()

    def is_near_duplicate(self, left: str, right: str, threshold: float = 0.88) -> bool:
        return self.similarity(left, right) >= threshold
