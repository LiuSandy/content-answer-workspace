"""RSS 工具；通过 feedparser 解析 RSS/Atom 订阅源，返回标准化采集卡片 JSON。"""

from __future__ import annotations

import json

from langchain_core.tools import tool

_PLATFORM = "rss"
_MAX_ITEMS = 20


def _to_result(topic: str, items: list[dict]) -> str:
    return json.dumps(
        {"platform": _PLATFORM, "topic": topic, "items": items[:_MAX_ITEMS]},
        ensure_ascii=False,
    )


def _error_result(topic: str, msg: str) -> str:
    return json.dumps({"platform": _PLATFORM, "topic": topic, "error": msg, "items": []}, ensure_ascii=False)


@tool
def rss_fetch(feed_url: str, max_entries: int = 10) -> str:
    """读取 RSS/Atom 订阅源，返回最新文章标题、链接、摘要等结构化结果。"""
    try:
        import feedparser  # type: ignore[import-untyped]
    except ImportError:
        return _error_result(feed_url, "feedparser 未安装，请运行 `uv add feedparser`")

    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            return _error_result(feed_url, f"无法解析订阅源：{feed_url}")

        feed_title = feed.feed.get("title", feed_url)
        entries = feed.entries[:min(max_entries, _MAX_ITEMS)]
        items = []
        for entry in entries:
            title = str(entry.get("title") or "")
            url = str(entry.get("link") or "")
            excerpt = str(entry.get("summary") or "")[:200]
            if title:
                items.append({"title": title, "url": url, "excerpt": excerpt, "metric": "", "author": ""})

        return _to_result(feed_title, items) if items else _error_result(feed_url, "订阅源无条目")
    except Exception as e:  # noqa: BLE001
        return _error_result(feed_url, str(e))
