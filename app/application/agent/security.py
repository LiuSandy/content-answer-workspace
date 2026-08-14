"""Agent 工具安全边界（spec §12）。

统一 URL 域名白名单：web_fetch / crawl4ai_fetch / firecrawl_scrape 共享同一套
SSRF 防护——初始 URL 与重定向的每一跳都重新做安全校验，且响应体大小受限。
复用知识库导入已有的 ssrf.py，保证"哪些地址不可访问"的安全策略只存在一处。
"""
from __future__ import annotations

from app.infrastructure.knowledge.ssrf import (
    SSRFError,
    fetch_url_safely,
    validate_url_security,
)

__all__ = ["SSRFError", "validate_web_fetch_url", "fetch_web_page"]


def validate_web_fetch_url(url: str) -> bool:
    """校验任意 Agent 抓取 URL：仅 http(s)，且解析出的所有 IP 均为公网地址。

    拒绝环回 / 私网 / link-local（含云元数据端点）/ CGNAT / 非 http(s) 协议。
    对不安全地址抛出 SSRFError。
    """
    return validate_url_security(url)


async def fetch_web_page(
    url: str,
    max_bytes: int = 10 * 1024 * 1024,
    timeout: float = 30.0,
) -> str:
    """SSRF 安全抓取网页文本；重定向逐跳重新校验，响应大小受限。"""
    return await fetch_url_safely(url, max_bytes=max_bytes, timeout=timeout)
