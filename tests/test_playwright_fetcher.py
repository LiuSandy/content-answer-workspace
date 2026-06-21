from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.collectors.fetchers.playwright_fetcher import (
    PlaywrightFetcher,
    parse_cookie_string,
)


class ParseCookieStringTests(unittest.TestCase):
    """覆盖 cookie 字符串转 Playwright cookie 字典的解析逻辑；这样注入登录态时字段格式不会出错。"""

    def test_parses_multiple_cookie_pairs_into_playwright_cookie_dicts(self) -> None:
        result = parse_cookie_string("a=1; b=2", domain=".xiaohongshu.com")
        self.assertEqual(
            result,
            [
                {"name": "a", "value": "1", "domain": ".xiaohongshu.com", "path": "/"},
                {"name": "b", "value": "2", "domain": ".xiaohongshu.com", "path": "/"},
            ],
        )

    def test_skips_malformed_pairs_without_equals_sign(self) -> None:
        result = parse_cookie_string("a=1; malformed; b=2", domain=".xiaohongshu.com")
        self.assertEqual([c["name"] for c in result], ["a", "b"])


class PlaywrightFetcherTests(unittest.IsolatedAsyncioTestCase):
    """覆盖 PlaywrightFetcher 的渲染编排；这样不需要真实浏览器也能验证 cookie 注入和返回值路径。"""

    async def test_fetch_injects_cookies_and_returns_rendered_html(self) -> None:
        fake_page = AsyncMock()
        fake_page.content = AsyncMock(return_value="<html>rendered</html>")
        fake_context = AsyncMock()
        fake_context.new_page = AsyncMock(return_value=fake_page)
        fake_browser = AsyncMock()
        fake_browser.new_context = AsyncMock(return_value=fake_context)
        fake_chromium = AsyncMock()
        fake_chromium.launch = AsyncMock(return_value=fake_browser)
        fake_playwright_instance = MagicMock()
        fake_playwright_instance.chromium = fake_chromium

        fake_playwright_cm = AsyncMock()
        fake_playwright_cm.__aenter__ = AsyncMock(return_value=fake_playwright_instance)
        fake_playwright_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.infrastructure.collectors.fetchers.playwright_fetcher.async_playwright",
            return_value=fake_playwright_cm,
        ):
            fetcher = PlaywrightFetcher(cookie_string="a=1", cookie_domain=".xiaohongshu.com")
            html = await fetcher.fetch(
                "https://www.xiaohongshu.com/search_result?keyword=test", {"User-Agent": "UA"}
            )

        self.assertEqual(html, "<html>rendered</html>")
        fake_context.add_cookies.assert_awaited_once_with(
            [{"name": "a", "value": "1", "domain": ".xiaohongshu.com", "path": "/"}]
        )
        fake_browser.close.assert_awaited_once()

    async def test_fetch_skips_cookie_injection_when_no_cookie_configured(self) -> None:
        fake_page = AsyncMock()
        fake_page.content = AsyncMock(return_value="<html>no-cookie</html>")
        fake_context = AsyncMock()
        fake_context.new_page = AsyncMock(return_value=fake_page)
        fake_browser = AsyncMock()
        fake_browser.new_context = AsyncMock(return_value=fake_context)
        fake_chromium = AsyncMock()
        fake_chromium.launch = AsyncMock(return_value=fake_browser)
        fake_playwright_instance = MagicMock()
        fake_playwright_instance.chromium = fake_chromium

        fake_playwright_cm = AsyncMock()
        fake_playwright_cm.__aenter__ = AsyncMock(return_value=fake_playwright_instance)
        fake_playwright_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.infrastructure.collectors.fetchers.playwright_fetcher.async_playwright",
            return_value=fake_playwright_cm,
        ):
            fetcher = PlaywrightFetcher()
            await fetcher.fetch("https://example.com", {"User-Agent": "UA"})

        fake_context.add_cookies.assert_not_called()


if __name__ == "__main__":
    unittest.main()
