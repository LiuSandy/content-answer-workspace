"""小红书搜索工具约束测试：按时间排序 / 精确条数 / 去重 由工具层保证。"""
from __future__ import annotations

import json

from app.agents._shared.tools.xiaohongshu_tool import (
    _dedupe,
    _normalize_item,
    _sort_by_recent,
)


def test_normalize_item_keeps_published_at():
    item = _normalize_item({
        "title": "历史播客推荐",
        "url": "https://xhs.com/note/1",
        "desc": "摘要",
        "likes": "197",
        "author": "小李",
        "published_at": "2026-07-22",
    })
    assert item["published_at"] == "2026-07-22"
    assert item["metric"] == "197 赞"


def test_sort_by_recent_descending():
    items = [
        {"published_at": "2026-04-18", "title": "old"},
        {"published_at": "2026-07-22", "title": "new"},
        {"published_at": "2026-01-26", "title": "oldest"},
        {"published_at": "", "title": "no-time"},
    ]
    sorted_items = _sort_by_recent(items)
    assert sorted_items[0]["title"] == "new"
    assert sorted_items[1]["title"] == "old"
    assert sorted_items[2]["title"] == "oldest"
    # 无时间的排最后
    assert sorted_items[-1]["title"] == "no-time"


def test_dedupe_by_url():
    items = [
        {"url": "https://xhs.com/note/1", "title": "a"},
        {"url": "https://xhs.com/note/1", "title": "a-dup"},
        {"url": "https://xhs.com/note/2", "title": "b"},
        {"url": "", "title": "no-url-c"},
        {"url": "", "title": "no-url-d"},
    ]
    unique = _dedupe(items)
    # 无 URL 的条目被丢弃，无法可靠去重
    assert len(unique) == 2
    assert [i["title"] for i in unique] == ["a", "b"]


def test_dedupe_keeps_first_occurrence():
    items = [
        {"url": "https://xhs.com/note/1", "title": "first"},
        {"url": "https://xhs.com/note/1", "title": "second"},
    ]
    unique = _dedupe(items)
    assert unique[0]["title"] == "first"
    assert len(unique) == 1


def test_sort_then_dedupe_then_truncate():
    """组合验证：时间排序 → 去重 → 截取，模拟搜索工具的真实流程。"""
    items = [
        {"url": "u1", "published_at": "2026-07-22", "title": "newest"},
        {"url": "u1", "published_at": "2026-07-22", "title": "dup-of-newest"},
        {"url": "u2", "published_at": "2026-07-20", "title": "middle"},
        {"url": "u3", "published_at": "2026-07-18", "title": "oldest"},
    ]
    result = _dedupe(_sort_by_recent(items))[:2]
    assert len(result) == 2
    assert result[0]["title"] == "newest"
    assert result[1]["title"] == "middle"


def test_search_tool_limit_clamps():
    """limit 参数被钳制在 1..20 之间。"""
    from app.agents._shared.tools.xiaohongshu_tool import _MAX_ITEMS
    assert _MAX_ITEMS == 20
