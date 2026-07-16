"""Tests for URL safety validation."""
from __future__ import annotations

import pytest

from nonebot_agent.utils.url_safety import UnsafeURLError, ensure_public_http_url


class TestURLSafety:
    """Test URL safety validation for outbound HTTP requests."""

    def test_allows_public_http_and_https_urls(self):
        """Public HTTP/HTTPS URLs should be allowed."""
        assert ensure_public_http_url("https://example.com/article?id=1") == "https://example.com/article?id=1"
        assert ensure_public_http_url("http://v.douyin.com/abc123/") == "http://v.douyin.com/abc123/"

    def test_rejects_blank_and_non_http_urls(self):
        """Blank URLs and non-HTTP schemes should be rejected."""
        unsafe_urls = [
            "",
            "   ",
            "file:///C:/Windows/win.ini",
            "ftp://example.com/file.zip",
        ]

        for url in unsafe_urls:
            with pytest.raises(UnsafeURLError):
                ensure_public_http_url(url)

    def test_rejects_localhost_and_private_network_urls(self):
        """Localhost and private network URLs should be rejected."""
        unsafe_urls = [
            "http://localhost:8080/debug",
            "http://127.0.0.1:8080/debug",
            "http://10.0.0.5/admin",
            "http://172.16.0.1/admin",
            "http://192.168.1.1/admin",
            "http://[::1]/debug",
            "http://169.254.169.254/latest/meta-data",
            "http://2130706433/admin",
            "http://0x7f000001/admin",
            "http://0177.0.0.1/admin",
        ]

        for url in unsafe_urls:
            with pytest.raises(UnsafeURLError):
                ensure_public_http_url(url)

    def test_rejects_urls_with_embedded_credentials(self):
        """URLs with embedded credentials should be rejected."""
        with pytest.raises(UnsafeURLError):
            ensure_public_http_url("https://user:pass@example.com/private")

    def test_strips_whitespace_from_url(self):
        """URLs with leading/trailing whitespace should be cleaned."""
        result = ensure_public_http_url("  https://example.com  ")
        assert result == "https://example.com"
