from __future__ import annotations

from langchain_core.tools import tool


@tool
async def crawl4ai_fetch(url: str) -> str:
    """使用 Crawl4AI 抓取网页并返回 LLM 友好的 Markdown 正文。
    支持 JavaScript 渲染页面，适合动态内容、单页应用等场景。
    比 web_fetch 更强大，但速度较慢（需启动浏览器）。"""
    from crawl4ai import AsyncWebCrawler

    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
        if not result.success:
            return f"抓取失败：{result.error_message}"
        content = result.markdown or result.cleaned_html or ""
        return content[:8000] if content else "页面内容为空"
    except Exception as e:
        return f"抓取失败：{e}"
