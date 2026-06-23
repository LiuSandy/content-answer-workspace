from __future__ import annotations

import os

from langchain_core.tools import tool

# 未配置 FIRECRAWL_API_KEY 时不加入 ALL_TOOLS，
# 需要 API key 时在 __init__.py 中取消注释并加入列表。


@tool
def firecrawl_scrape(url: str) -> str:
    """使用 Firecrawl 抓取网页并返回 Markdown 正文。
    支持 JS 渲染、反爬绕过，适合复杂网站。需要 FIRECRAWL_API_KEY 环境变量。"""
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
