from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.agents._shared.tools import zhihu_tool
from app.api.schemas.workflow import QuestionItem


@pytest.mark.asyncio
async def test_zhihu_search_uses_web_collector(monkeypatch):
    """明确的知乎搜索必须使用 tools 中配置的网页采集路径。"""

    web_item = QuestionItem(
        id="42",
        platform="zhihu",
        title="知乎网页采集结果",
        url="https://www.zhihu.com/question/42",
        answerCount=8,
        excerpt="网页摘要",
        detail="",
        topic="知乎热门问题",
    )
    monkeypatch.setattr(
        zhihu_tool,
        "search_zhihu_for_keyword",
        AsyncMock(return_value=[web_item]),
    )

    raw = await zhihu_tool.zhihu_search.ainvoke({"keyword": "知乎热门问题", "limit": 5})
    result = json.loads(raw)

    assert result == {
        "platform": "zhihu",
        "mode": "web",
        "topic": "知乎热门问题",
        "items": [
            {
                "title": "知乎网页采集结果",
                "url": "https://www.zhihu.com/question/42",
                "excerpt": "网页摘要",
                "answer_count": 8,
            }
        ],
    }


@pytest.mark.asyncio
async def test_zhihu_search_marks_authentication_failure_as_non_retryable(monkeypatch):
    monkeypatch.setattr(
        zhihu_tool,
        "search_zhihu_for_keyword",
        AsyncMock(side_effect=ValueError("401 ERR_TICKET_NOT_EXIST")),
    )

    raw = await zhihu_tool.zhihu_search.ainvoke({"keyword": "热门", "limit": 5})
    result = json.loads(raw)

    assert result == {
        "platform": "zhihu",
        "topic": "热门",
        "error": "401 ERR_TICKET_NOT_EXIST",
        "error_code": "zhihu_auth_invalid",
        "retryable": False,
        "message": "知乎登录凭据已失效，请更新 Cookie 和请求签名后重试。",
        "items": [],
    }


@pytest.mark.asyncio
async def test_zhihu_search_treats_missing_signature_as_authentication_failure(monkeypatch):
    monkeypatch.setattr(
        zhihu_tool,
        "search_zhihu_for_keyword",
        AsyncMock(side_effect=ValueError("当前缺少：ZHIHU_X_ZSE_96")),
    )

    raw = await zhihu_tool.zhihu_search.ainvoke({"keyword": "个人网站", "limit": 5})
    result = json.loads(raw)

    assert result["error_code"] == "zhihu_auth_invalid"
    assert result["retryable"] is False
    assert "登录凭据" in result["message"]


@pytest.mark.asyncio
async def test_zhihu_hot_search_fetches_candidates_and_returns_most_answered(monkeypatch):
    items = [
        QuestionItem(
            id=str(index),
            title=f"问题{index}",
            url=f"https://www.zhihu.com/question/{index}",
            answerCount=answer_count,
            topic="个人网站",
        )
        for index, answer_count in ((1, 3), (2, 30), (3, 12))
    ]
    search = AsyncMock(return_value=items)
    monkeypatch.setattr(zhihu_tool, "search_zhihu_for_keyword", search)

    raw = await zhihu_tool.zhihu_search.ainvoke(
        {"keyword": "个人网站", "limit": 2, "sort": "hot"}
    )
    result = json.loads(raw)

    search.assert_awaited_once()
    assert search.await_args.kwargs["limit"] == 8
    assert [item["title"] for item in result["items"]] == ["问题2", "问题3"]
