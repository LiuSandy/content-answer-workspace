"""RSS 工具；通过 feedparser 解析 RSS/Atom 订阅源，无需额外 CLI。"""

from __future__ import annotations

from langchain_core.tools import tool

_PLATFORM = "rss"
_MAX_CHARS = 6000
_MAX_ENTRIES = 20


@tool
def rss_fetch(feed_url: str, max_entries: int = 10) -> str:
    """读取 RSS/Atom 订阅源，返回最新文章列表（标题、链接、摘要）。"""
    try:
        import feedparser  # type: ignore[import-untyped]
    except ImportError:
        return f"[{_PLATFORM}] feedparser 未安装，请运行 `uv add feedparser`。"

    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            return f"[{_PLATFORM}] 无法解析订阅源：{feed_url}"

        entries = feed.entries[:min(max_entries, _MAX_ENTRIES)]
        lines = [f"# {feed.feed.get('title', feed_url)}\n"]
        for entry in entries:
            title = entry.get("title", "无标题")
            link = entry.get("link", "")
            summary = entry.get("summary", "")[:200]
            lines.append(f"- **{title}**\n  {link}\n  {summary}")

        return "\n".join(lines)[:_MAX_CHARS]
    except Exception as e:  # noqa: BLE001
        return f"[{_PLATFORM}] 解析失败：{e}"
