from __future__ import annotations

from langchain_core.tools import tool

from app.shared.agent import security


@tool
async def crawl4ai_fetch(url: str) -> str:
    """使用 Crawl4AI 抓取网页并返回 LLM 友好的 Markdown 正文。
    支持 JavaScript 渲染页面，适合动态内容、单页应用等场景。
    比 web_fetch 更强大，但速度较慢（需启动浏览器）。
    仅允许公网地址（SSRF 防护），内网 / 环回 / 云元数据地址会被拒绝。"""
    try:
        security.validate_web_fetch_url(url)
    except security.SSRFError as e:
        return f"抓取失败：该地址被安全策略拒绝（{e}）"

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
