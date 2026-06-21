from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
_MAX_CHARS = 5000


@tool
def web_fetch(url: str) -> str:
    """抓取指定 URL 的网页正文内容，去除导航、脚本等无关元素，返回纯文本。"""
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers=_HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:_MAX_CHARS]
    except Exception as e:
        return f"抓取失败：{e}"
