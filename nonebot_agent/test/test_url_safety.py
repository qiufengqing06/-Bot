"""Tests for outbound URL safety checks."""
from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from nonebot_agent.utils.url_safety import UnsafeURLError, ensure_public_http_url
except ModuleNotFoundError:
    class UnsafeURLError(ValueError):
        pass

    def ensure_public_http_url(url: str) -> str:
        raise AssertionError("nonebot_agent.utils.url_safety is not implemented")


class UrlSafetyTests(unittest.TestCase):
    def test_allows_public_http_and_https_urls(self):
        self.assertEqual(
            ensure_public_http_url(" https://example.com/article?id=1 "),
            "https://example.com/article?id=1",
        )
        self.assertEqual(
            ensure_public_http_url("http://v.douyin.com/abc123/"),
            "http://v.douyin.com/abc123/",
        )

    def test_rejects_blank_and_non_http_urls(self):
        unsafe_urls = [
            "",
            "   ",
            "file:///C:/Windows/win.ini",
            "ftp://example.com/file.zip",
        ]

        for url in unsafe_urls:
            with self.subTest(url=url):
                with self.assertRaises(UnsafeURLError):
                    ensure_public_http_url(url)

    def test_rejects_localhost_and_private_network_urls(self):
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
            with self.subTest(url=url):
                with self.assertRaises(UnsafeURLError):
                    ensure_public_http_url(url)

    def test_rejects_urls_with_embedded_credentials(self):
        with self.assertRaises(UnsafeURLError):
            ensure_public_http_url("https://user:pass@example.com/private")

    def test_webpage_tool_rejects_unsafe_url_without_request(self):
        from nonebot_agent.tools.webpage import read_webpage

        with patch("nonebot_agent.tools.webpage.requests.get") as request_get:
            result = read_webpage.invoke({"url": "http://127.0.0.1:8080/debug"})

        request_get.assert_not_called()
        self.assertIn("URL rejected", result)

    def test_bilibili_card_rejects_private_network_url(self):
        from nonebot_agent.plugins.video_download import detect_bilibili_card

        raw_message = (
            '[CQ:json,data={"meta":{"detail_1":{"appid":"1109937557"'
            ',"qqdocurl":"http:\\/\\/127.0.0.1:8080\\/video"'
            ',"title":"local","desc":"debug"}}}]'
        ).replace(",", "&#44;")

        self.assertIsNone(detect_bilibili_card(raw_message))


if __name__ == "__main__":
    unittest.main()
