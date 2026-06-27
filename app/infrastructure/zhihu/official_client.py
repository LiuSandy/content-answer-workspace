from __future__ import annotations

import os
import time
from typing import Any

import httpx

from ...config.loader import get_settings
from ...core.config import get_required_env

BASE_URL = "https://developer.zhihu.com"


class ZhihuOfficialClient:
    """封装知乎官方 API HTTP 调用；这样鉴权逻辑集中在一处，采集器和热榜服务都可以复用。"""

    def __init__(self) -> None:
        self._access_secret: str | None = None

    def _get_access_secret(self) -> str:
        if not self._access_secret:
            self._access_secret = get_required_env("ZHIHU_ACCESS_SECRET")
        return self._access_secret

    def _get_auth_headers(self) -> dict[str, str]:
        """构建官方鉴权头；Bearer Token 和秒级时间戳只在此处生成，不散落在调用方。"""
        return {
            "Authorization": f"Bearer {self._get_access_secret()}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }

    async def search(self, query: str, count: int = 10) -> dict[str, Any]:
        """调用知乎站内搜索 API；这样官方搜索结果由此处统一获取，不依赖 cookie 或逆向签名。"""
        params = {"Query": query, "Count": min(count, 10)}
        async with httpx.AsyncClient(timeout=get_settings().http.client_timeout_seconds) as client:
            response = await client.get(
                f"{BASE_URL}/api/v1/content/zhihu_search",
                params=params,
                headers=self._get_auth_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get_hotlist(self, limit: int = 30) -> dict[str, Any]:
        """调用知乎热榜 API；这样热榜数据获取不依赖任何 cookie 凭据。"""
        params = {"Limit": min(limit, get_settings().hotlist.max_limit)}
        async with httpx.AsyncClient(timeout=get_settings().http.client_timeout_seconds) as client:
            response = await client.get(
                f"{BASE_URL}/api/v1/content/hot_list",
                params=params,
                headers=self._get_auth_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def web_search(self, query: str, count: int = 10, search_db: str = "all") -> dict[str, Any]:
        """调用全网搜索 API；这样站外参考资料可以通过官方渠道补充，不走第三方搜索。"""
        params = {"Query": query, "Count": min(count, 10), "SearchDB": search_db}
        async with httpx.AsyncClient(timeout=get_settings().http.client_timeout_seconds) as client:
            response = await client.get(
                f"{BASE_URL}/api/v1/content/global_search",
                params=params,
                headers=self._get_auth_headers(),
            )
            response.raise_for_status()
            return response.json()
