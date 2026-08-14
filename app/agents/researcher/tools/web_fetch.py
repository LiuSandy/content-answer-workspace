from __future__ import annotations

from bs4 import BeautifulSoup
from langchain_core.tools import tool

from app.agents._shared import security

_MAX_CHARS = 5000


@tool
async def web_fetch(url: str) -> str:
    """抓取指定 URL 的网页正文内容，去除导航、脚本等无关元素，返回纯文本。

    仅允许公网地址（SSRF 防护）：内网 / 环回 / 云元数据等不安全地址会被拒绝，
    重定向的每一跳都会重新做安全校验，响应体大小受限。
    """
    try:
        text = await security.fetch_web_page(url)
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        content = soup.get_text(separator="\n", strip=True)
        return content[:_MAX_CHARS] if content else "页面内容为空"
    except Exception as e:
        return f"抓取失败：{e}"
