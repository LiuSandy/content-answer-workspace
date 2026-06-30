"""知乎搜索工具；优先调用官方 API，失败时自动降级到 Cookie 爬取模式。"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from ....config.loader import get_settings
from ....infrastructure.zhihu.official_client import ZhihuOfficialClient
from ....models import Topic
from ....services.zhihu_service import search_zhihu_for_keyword

logger = logging.getLogger(__name__)

_PLATFORM = "zhihu"
_MAX_ITEMS = 20


def _map_official_results(raw: dict, keyword: str) -> list[dict]:
    """将官方 API 响应映射为统一输出格式；与 Cookie 模式的输出结构保持一致。"""
    data = raw.get("Data") or raw.get("data") or {}
    entries = data.get("Items") or data.get("items") or []
    if not isinstance(entries, list):
        return []

    results = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = entry.get("Url") or entry.get("url") or ""
        title = (entry.get("Title") or entry.get("title") or "").replace(" - 知乎", "").strip()
        excerpt = entry.get("ContentText") or entry.get("excerpt") or ""
        if not title:
            continue
        results.append({"title": title, "url": url, "excerpt": excerpt[:200]})

    return results[:_MAX_ITEMS]


def _map_question_items(items) -> list[dict]:
    """将内部 QuestionItem 列表映射为统一输出格式。"""
    return [
        {
            "title": item.title,
            "url": item.url,
            "excerpt": (item.excerpt or "")[:200],
            "answer_count": item.answer_count,
        }
        for item in items[:_MAX_ITEMS]
    ]


@tool
async def zhihu_search(keyword: str, limit: int = 10) -> str:
    """在知乎搜索与关键词相关的问题，返回结构化 JSON（标题、链接、摘要）。
    优先使用官方 API，不可用时自动降级为网页爬取模式。"""
    user_agent = get_settings().http.user_agent

    # 优先：官方 API 模式
    try:
        client = ZhihuOfficialClient()
        raw = await client.search(keyword, count=min(limit, 10))
        items = _map_official_results(raw, keyword)
        if items:
            return json.dumps(
                {"platform": _PLATFORM, "mode": "official", "topic": keyword, "items": items},
                ensure_ascii=False,
            )
        logger.info("[zhihu] 官方 API 返回空结果，降级到 Cookie 模式")
    except Exception as exc:
        logger.warning("[zhihu] 官方 API 失败（%s），降级到 Cookie 模式", exc)

    # 降级：Cookie 爬取模式
    try:
        topic = Topic(id=keyword, name=keyword, keywords=[])
        raw_items = await search_zhihu_for_keyword(topic, keyword, user_agent, limit=limit)
        items = _map_question_items(raw_items)
        return json.dumps(
            {"platform": _PLATFORM, "mode": "web", "topic": keyword, "items": items},
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {"platform": _PLATFORM, "error": str(exc), "topic": keyword, "items": []},
            ensure_ascii=False,
        )
