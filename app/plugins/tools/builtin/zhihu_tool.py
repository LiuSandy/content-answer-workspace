"""知乎搜索工具；使用知乎开放平台站内搜索 API 获取内容。"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from app.platform.config.loader import get_settings
from app.shared.content import Topic
from app.plugins.sources.zhihu_service import search_zhihu_for_keyword

logger = logging.getLogger(__name__)

_PLATFORM = "zhihu"
_MAX_ITEMS = 20


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
async def zhihu_search(keyword: str, limit: int = 10, sort: str = "relevance") -> str:
    """在知乎搜索与关键词相关的问题，返回结构化 JSON（标题、链接、摘要）。
    数据只通过网页采集模式获取。"""
    user_agent = get_settings().http.user_agent

    try:
        requested_limit = max(1, min(_MAX_ITEMS, int(limit)))
        normalized_sort = sort if sort in {"relevance", "hot", "latest"} else "relevance"
        candidate_limit = (
            min(_MAX_ITEMS, max(requested_limit, requested_limit * 4))
            if normalized_sort in {"hot", "latest"}
            else requested_limit
        )
        topic = Topic(id=keyword, name=keyword, keywords=[])
        raw_items = await search_zhihu_for_keyword(
            topic, keyword, user_agent, limit=candidate_limit
        )
        if normalized_sort == "hot":
            raw_items.sort(key=lambda item: item.answer_count or 0, reverse=True)
        elif normalized_sort == "latest":
            raw_items.sort(key=lambda item: item.updated_time or "", reverse=True)
        items = _map_question_items(raw_items)[:requested_limit]
        return json.dumps(
            {"platform": _PLATFORM, "mode": "web", "topic": keyword, "items": items},
            ensure_ascii=False,
        )
    except Exception as exc:
        error = str(exc)
        auth_markers = (
            "401",
            "20001",
            "ERR_TICKET",
            "AuthenticationInvalidRequest",
            "ZHIHU_ACCESS_SECRET",
            "ZHIHU_COOKIE_FILE",
        )
        error_code = (
            "zhihu_auth_invalid"
            if any(marker in error for marker in auth_markers)
            else "zhihu_search_failed"
        )
        message = (
            "知乎登录凭据已失效，请更新 Cookie 和请求签名后重试。"
            if error_code == "zhihu_auth_invalid"
            else "知乎检索失败，请稍后重试。"
        )
        logger.exception(
            "Zhihu search failed: keyword=%r error_code=%s error=%s",
            keyword,
            error_code,
            error,
        )
        return json.dumps(
            {
                "platform": _PLATFORM,
                "error": error,
                "error_code": error_code,
                "retryable": False,
                "message": message,
                "topic": keyword,
                "items": [],
            },
            ensure_ascii=False,
        )
