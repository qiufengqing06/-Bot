"""Lightweight reference retrieval for multi-file skills."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from nonebot_agent.config import config
from nonebot_agent.skills.models import SkillSpec


REFERENCE_EXTENSIONS = {".md", ".txt", ".json"}
SKIP_DIRS = {"scripts", ".git", "__pycache__"}


@dataclass
class SkillReferenceChunk:
    """A searchable chunk from a skill support file."""

    skill_name: str
    path: str
    content: str
    score: int = 0


def _tokens(text: str) -> set[str]:
    lowered = (text or "").lower()
    tokens = set(re.findall(r"[a-z0-9_-]{2,}", lowered))

    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        tokens.update(sequence[index:index + 2] for index in range(len(sequence) - 1))
        if len(sequence) <= 4:
            tokens.add(sequence)

    return {token for token in tokens if token.strip()}


def _chunk_text(text: str, chunk_size: int) -> Iterable[str]:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks = []
    step = max(chunk_size - 120, 200)
    for start in range(0, len(cleaned), step):
        chunk = cleaned[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


class SkillReferenceIndex:
    """In-memory index for local skill reference files."""

    def __init__(self) -> None:
        self._cache: Dict[str, List[SkillReferenceChunk]] = {}

    def clear(self) -> None:
        self._cache.clear()

    def chunks_for(self, skill: SkillSpec) -> List[SkillReferenceChunk]:
        if skill.name in self._cache:
            return self._cache[skill.name]

        root_dir = Path(skill.root_dir) if skill.root_dir else Path(skill.source).parent
        chunks: List[SkillReferenceChunk] = []
        if root_dir.exists():
            for path in sorted(root_dir.rglob("*"), key=lambda item: str(item).lower()):
                if not path.is_file() or path.suffix.lower() not in REFERENCE_EXTENSIONS:
                    continue
                if path.name == "SKILL.md":
                    continue
                if any(part in SKIP_DIRS for part in path.parts):
                    continue

                try:
                    text = path.read_text(encoding="utf-8")
                except Exception:
                    continue

                max_file_chars = max(1000, config.SKILLS_REFERENCE_MAX_FILE_CHARS)
                text = text[:max_file_chars]
                rel_path = str(path.relative_to(root_dir)).replace("\\", "/")
                for chunk in _chunk_text(text, config.SKILLS_REFERENCE_CHUNK_CHARS):
                    chunks.append(
                        SkillReferenceChunk(
                            skill_name=skill.name,
                            path=rel_path,
                            content=chunk,
                        )
                    )

        self._cache[skill.name] = chunks
        return chunks

    def search(self, skill: SkillSpec, query: str, top_k: int) -> List[SkillReferenceChunk]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []

        scored: List[SkillReferenceChunk] = []
        for chunk in self.chunks_for(skill):
            chunk_tokens = _tokens(chunk.path + "\n" + chunk.content)
            overlap = query_tokens.intersection(chunk_tokens)
            if not overlap:
                continue
            score = len(overlap)
            if any(token in chunk.path.lower() for token in query_tokens):
                score += 2
            scored.append(
                SkillReferenceChunk(
                    skill_name=chunk.skill_name,
                    path=chunk.path,
                    content=chunk.content,
                    score=score,
                )
            )

        scored.sort(key=lambda item: (-item.score, item.path))
        return scored[:top_k]


def format_reference_chunks(chunks: Iterable[SkillReferenceChunk], max_chars: int) -> str:
    sections = []
    for chunk in chunks:
        sections.append(f"[{chunk.path}]\n{chunk.content.strip()}")

    if not sections:
        return ""

    text = "\n\n".join(sections)
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n...[reference snippets truncated]"
    return text
