"""Tests for startup configuration validation."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from nonebot_agent.config_validation import (
    RuntimeConfigError,
    assert_runtime_config,
    validate_runtime_config,
)


def make_config(**overrides):
    values = {
        "LLM_MODEL": "deepseek-chat",
        "LLM_API_KEY": "llm-key",
        "LLM_API_URL": "https://api.example.com/v1",
        "IS_MULTIMODAL_MODEL": True,
        "VISION_MODEL": "qwen-vl",
        "VISION_API_KEY": "",
        "VISION_API_URL": "https://vision.example.com/v1",
        "QIANWEN_API_KEY": "qianwen-key",
        "DB_URL": "mysql+pymysql://root:pass@localhost:3306/nonebot_agent?charset=utf8mb4",
        "WEB_SEARCH_API_KEY": "",
        "WEB_SEARCH_API_URL": "",
        "DOUBAO_API_KEY": "",
        "DOUBAO_API_URL": "",
        "SKILLS_ALLOW_LOCAL_CODE": False,
        "SKILLS_SCRIPT_PYTHON": "python",
        "SKILLS_SCRIPT_ALLOWLIST": "",
        "VIDEO_DOWNLOAD_ENABLED": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ConfigValidationTests(unittest.TestCase):
    def test_reports_missing_core_startup_values_as_errors(self):
        issues = validate_runtime_config(
            make_config(
                LLM_MODEL="",
                LLM_API_KEY="",
                LLM_API_URL="",
                QIANWEN_API_KEY="",
                DB_URL="",
            )
        )

        error_keys = {issue.key for issue in issues if issue.level == "error"}

        self.assertEqual(
            error_keys,
            {"LLM_MODEL", "LLM_API_KEY", "LLM_API_URL", "QIANWEN_API_KEY", "DB_URL"},
        )

    def test_requires_vision_config_only_for_text_only_main_model(self):
        text_only_issues = validate_runtime_config(
            make_config(IS_MULTIMODAL_MODEL=False, VISION_API_KEY="")
        )
        multimodal_issues = validate_runtime_config(
            make_config(IS_MULTIMODAL_MODEL=True, VISION_API_KEY="")
        )

        self.assertIn(
            "VISION_API_KEY",
            {issue.key for issue in text_only_issues if issue.level == "error"},
        )
        self.assertNotIn(
            "VISION_API_KEY",
            {issue.key for issue in multimodal_issues if issue.level == "error"},
        )

    def test_optional_integrations_are_warnings_not_startup_errors(self):
        issues = validate_runtime_config(
            make_config(
                WEB_SEARCH_API_KEY="",
                WEB_SEARCH_API_URL="",
                DOUBAO_API_KEY="",
                DOUBAO_API_URL="",
            )
        )

        self.assertFalse([issue for issue in issues if issue.level == "error"])
        warning_keys = {issue.key for issue in issues if issue.level == "warning"}
        self.assertIn("WEB_SEARCH_API_KEY", warning_keys)
        self.assertIn("DOUBAO_API_KEY", warning_keys)

    def test_assert_runtime_config_raises_with_all_error_keys(self):
        with self.assertRaises(RuntimeConfigError) as captured:
            assert_runtime_config(make_config(LLM_API_KEY="", QIANWEN_API_KEY=""))

        message = str(captured.exception)
        self.assertIn("LLM_API_KEY", message)
        self.assertIn("QIANWEN_API_KEY", message)


if __name__ == "__main__":
    unittest.main()
