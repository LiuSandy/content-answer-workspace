from __future__ import annotations

import httpx


class HttpFetcher:
    """使用 httpx 发起 HTTP 请求获取页面；负责超时设置、Cookie 注入。"""

    def __init__(self, cookie_string: str | None = None) -> None:
        self._cookie_string = cookie_string

    async def fetch(self, url: str, headers: dict[str, str]) -> str:
        merged = dict(headers)
        if self._cookie_string:
            merged["Cookie"] = self._cookie_string
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers=merged)
            response.raise_for_status()
            return response.text
