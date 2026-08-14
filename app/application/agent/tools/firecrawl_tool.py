from __future__ import annotations

import os

from langchain_core.tools import tool

from ...agent import security

# 未配置 FIRECRAWL_API_KEY 时不加入 ALL_TOOLS，
# 需要 API key 时在 __init__.py 中取消注释并加入列表。


@tool
def firecrawl_scrape(url: str) -> str:
    """使用 Firecrawl 抓取网页并返回 Markdown 正文。
    支持 JS 渲染、反爬绕过，适合复杂网站。需要 FIRECRAWL_API_KEY 环境变量。
    仅允许公网地址（SSRF 防护），内网 / 环回 / 云元数据地址会被拒绝。"""
    try:
        security.validate_web_fetch_url(url)
    except security.SSRFError as e:
        return f"抓取失败：该地址被安全策略拒绝（{e}）"

    from firecrawl import FirecrawlApp

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return "未配置 FIRECRAWL_API_KEY，请在 .env 中设置后重启服务。"
    try:
        app = FirecrawlApp(api_key=api_key)
        result = app.scrape_url(url, formats=["markdown"])
        content = result.markdown or ""
        return content[:8000] if content else "页面内容为空"
    except Exception as e:
        return f"抓取失败：{e}"
