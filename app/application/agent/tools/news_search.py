from __future__ import annotations

from langchain_core.tools import tool


@tool
def news_search(query: str, max_results: int = 5) -> str:
    """搜索最新新闻，返回标题、摘要、来源和发布时间。适合查询热点事件、行业动态。"""
    try:
        from ddgs import DDGS

        results = DDGS().news(query, max_results=max_results)
        if not results:
            return "未找到相关新闻。"
        lines: list[str] = []
        for item in results:
            lines.append(f"标题：{item.get('title', '')}")
            lines.append(f"来源：{item.get('source', '')} | 时间：{item.get('date', '')}")
            lines.append(f"摘要：{item.get('body', '')}")
            lines.append(f"链接：{item.get('url', '')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"新闻搜索失败：{e}"
