"""Tests for configuration validation."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from nonebot_agent.config_validation import (
    ConfigIssue,
    RuntimeConfigError,
    validate_runtime_config,
    format_config_issues,
)


class TestConfigValidation:
    """Test runtime configuration validation."""

    def test_validate_detects_missing_required_fields(self):
        """Missing required fields should be detected."""
        config = MagicMock()
        config.LLM_MODEL = ""
        config.LLM_API_KEY = ""
        config.LLM_API_URL = ""
        config.QIANWEN_API_KEY = ""
        config.DB_URL = ""
        config.IS_MULTIMODAL_MODEL = True
        config.SKILLS_ALLOW_LOCAL_CODE = False
        
        issues = validate_runtime_config(config)
        
        errors = [issue for issue in issues if issue.level == "error"]
        assert len(errors) > 0
        assert any(issue.key == "LLM_MODEL" for issue in errors)

    def test_validate_passes_with_valid_config(self):
        """Valid configuration should have no errors."""
        config = MagicMock()
        config.LLM_MODEL = "test-model"
        config.LLM_API_KEY = "test-key"
        config.LLM_API_URL = "https://api.test.com"
        config.QIANWEN_API_KEY = "test-key"
        config.DB_URL = "mysql://test"
        config.IS_MULTIMODAL_MODEL = True
        config.SKILLS_ALLOW_LOCAL_CODE = False
        config.WEB_SEARCH_API_KEY = "test"
        config.WEB_SEARCH_API_URL = "test"
        config.DOUBAO_API_KEY = "test"
        config.DOUBAO_API_URL = "test"
        
        issues = validate_runtime_config(config)
        
        errors = [issue for issue in issues if issue.level == "error"]
        assert len(errors) == 0

    def test_validate_warns_about_optional_features(self):
        """Missing optional features should generate warnings."""
        config = MagicMock()
        config.LLM_MODEL = "test-model"
        config.LLM_API_KEY = "test-key"
        config.LLM_API_URL = "https://api.test.com"
        config.QIANWEN_API_KEY = "test-key"
        config.DB_URL = "mysql://test"
        config.IS_MULTIMODAL_MODEL = True
        config.SKILLS_ALLOW_LOCAL_CODE = False
        config.WEB_SEARCH_API_KEY = ""
        config.WEB_SEARCH_API_URL = ""
        config.DOUBAO_API_KEY = ""
        config.DOUBAO_API_URL = ""
        
        issues = validate_runtime_config(config)
        
        warnings = [issue for issue in issues if issue.level == "warning"]
        assert len(warnings) > 0

    def test_format_config_issues_creates_readable_output(self):
        """Format should create human-readable output."""
        issues = [
            ConfigIssue(level="error", key="LLM_MODEL", message="Model is required"),
            ConfigIssue(level="warning", key="API_KEY", message="Key is missing"),
        ]
        
        formatted = format_config_issues(issues)
        
        assert "ERROR" in formatted
        assert "WARN" in formatted
        assert "LLM_MODEL" in formatted
        assert "API_KEY" in formatted

    def test_format_config_issues_empty_returns_success(self):
        """Empty issues list should return success message."""
        formatted = format_config_issues([])
        assert "通过" in formatted
