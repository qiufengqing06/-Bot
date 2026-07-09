"""Structured memory unit tests."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from nonebot_agent.memory.memory_deduper import MemoryDeduper
from nonebot_agent.memory.memory_store import StructuredMemoryStore
from nonebot_agent.memory.memory_summary import MemorySummaryManager
from nonebot_agent.memory.memory_writer import MemoryWriter


class FakeChroma:
    def __init__(self):
        self.calls = []

    def search_memory(self, **kwargs):
        self.calls.append(kwargs)
        return []


class MemoryWriterTests(unittest.TestCase):
    def setUp(self):
        self.writer = MemoryWriter()

    def test_build_candidates_extracts_fact_and_event(self):
        text = (
            "\u6211\u53eb\u5c0f\u660e\uff0c"
            "\u6211\u6700\u8fd1\u5728\u51c6\u5907\u8003\u7814\uff0c"
            "\u6211\u559c\u6b22\u706b\u9505"
        )

        candidates = self.writer.build_candidates(text)

        self.assertTrue(any(item.memory_type == "fact" and item.slot_key == "name" for item in candidates))
        self.assertTrue(any(item.memory_type == "fact" and item.slot_key == "like" for item in candidates))
        self.assertTrue(any(item.memory_type == "event" for item in candidates))

    def test_build_candidates_skips_question_like_input(self):
        text = "\u6211\u559c\u6b22\u5403\u4ec0\u4e48\uff1f"

        candidates = self.writer.build_candidates(text)

        self.assertEqual(candidates, [])


class MemoryDeduperTests(unittest.TestCase):
    def test_near_duplicate_detection(self):
        deduper = MemoryDeduper()

        self.assertTrue(
            deduper.is_near_duplicate(
                "\u7528\u6237\u559c\u6b22\uff1a\u706b\u9505",
                "\u7528\u6237\u559c\u6b22\u706b\u9505",
                threshold=0.75,
            )
        )


class MemoryStoreTests(unittest.TestCase):
    def test_search_uses_mode_filter(self):
        chroma = FakeChroma()
        store = StructuredMemoryStore(chroma=chroma, writer=MemoryWriter(), deduper=MemoryDeduper())

        store.search_facts("user-1", "query", 3, source_mode="chat")
        store.search_events("user-1", "query", 2, group_id="group-1", source_mode="professional")

        self.assertEqual(chroma.calls[0]["mode"], "chat")
        self.assertEqual(chroma.calls[0]["extra_filters"]["memory_type"], "fact")
        self.assertEqual(chroma.calls[1]["mode"], "professional")
        self.assertEqual(chroma.calls[1]["extra_filters"]["group_id"], "group-1")


class MemorySummaryTests(unittest.TestCase):
    def test_build_summary_collects_recent_user_topics(self):
        manager = MemorySummaryManager()
        messages = [
            SimpleNamespace(role="user", content="\u6211\u6700\u8fd1\u5728\u5b66Python"),
            SimpleNamespace(role="assistant", content="ok"),
            SimpleNamespace(role="user", content="\u6211\u60f3\u627e\u5b9e\u4e60"),
        ]

        summary = manager.build_summary(messages)

        self.assertIn("\u6211\u6700\u8fd1\u5728\u5b66Python", summary)
        self.assertIn("\u6211\u60f3\u627e\u5b9e\u4e60", summary)


if __name__ == "__main__":
    unittest.main()
