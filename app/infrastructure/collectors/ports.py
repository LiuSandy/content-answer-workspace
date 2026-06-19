from __future__ import annotations

from typing import Protocol


class FetcherPort(Protocol):
    """页面获取器接口：只负责把 URL 变成 HTML 字符串。"""

    async def fetch(self, url: str, headers: dict[str, str]) -> str:
        """获取页面 HTML，失败时抛出异常。"""
        ...


class ExtractorPort(Protocol):
    """内容提取器接口：只负责把文本变成结构化列表。"""

    async def extract(self, text: str, prompt: str) -> list[dict[str, str]]:
        """按 prompt 描述从文本中提取条目，返回 dict 列表。"""
        ...
