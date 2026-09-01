from __future__ import annotations

from playwright.async_api import async_playwright

from app.platform.config.loader import get_settings


def parse_cookie_string(cookie_string: str, domain: str) -> list[dict[str, str]]:
    """把 `a=1; b=2` 形式的 cookie 字符串转成 Playwright 需要的 cookie 字典列表。"""

    cookies: list[dict[str, str]] = []
    for pair in cookie_string.split(";"):
        if "=" not in pair:
            continue
        name, _, value = pair.strip().partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append({"name": name, "value": value, "domain": domain, "path": "/"})
    return cookies


class PlaywrightFetcher:
    """使用 Playwright 渲染页面获取最终 DOM HTML；负责 Cookie 注入和等待页面渲染完成。"""

    def __init__(self, cookie_string: str | None = None, cookie_domain: str = "") -> None:
        self._cookie_string = cookie_string
        self._cookie_domain = cookie_domain

    async def fetch(self, url: str, headers: dict[str, str]) -> str:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=headers.get("User-Agent"))
                if self._cookie_string and self._cookie_domain:
                    await context.add_cookies(parse_cookie_string(self._cookie_string, self._cookie_domain))
                page = await context.new_page()
                settings = get_settings().playwright
                await page.goto(url, wait_until="domcontentloaded", timeout=settings.goto_timeout_ms)
                await page.wait_for_timeout(settings.render_wait_ms)
                return await page.content()
            finally:
                await browser.close()
