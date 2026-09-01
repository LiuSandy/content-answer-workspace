from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.shared.content import Topic
from app.plugins.sources import zhihu_service


@pytest.mark.asyncio
async def test_search_zhihu_for_keyword_uses_official_api(monkeypatch) -> None:
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "test-secret")

    class FakeResponse:
        status_code = 200
        is_error = False

        def json(self):
            return {
                "Code": 0,
                "Message": "success",
                "Data": {
                    "Items": [
                        {
                            "Title": "个人网站建设有哪些方案",
                            "ContentType": "Question",
                            "ContentID": "123",
                            "ContentText": "摘要<em>内容</em>",
                            "Url": "https://www.zhihu.com/question/123/answer/456?utm_medium=openapi_platform&utm_source=2cc8fff",
                            "EditTime": 1748355858,
                        }
                    ]
                },
            }

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] > 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, *, params, headers):
            assert url == "https://developer.zhihu.com/api/v1/content/zhihu_search"
            assert params == {"Query": "个人网站", "Count": 10}
            assert headers["Authorization"] == "Bearer test-secret"
            assert headers["X-Request-Timestamp"].isdigit()
            return FakeResponse()

    monkeypatch.setattr(zhihu_service.httpx, "AsyncClient", FakeClient)

    items = await zhihu_service.search_zhihu_for_keyword(
        Topic(id="personal-site", name="个人网站", keywords=[]),
        "个人网站",
        "test-agent",
        limit=10,
    )

    assert [item.id for item in items] == ["123"]
    assert items[0].excerpt == "摘要 内容"
    assert items[0].url == "https://www.zhihu.com/question/123/answer/456"


def test_normalize_zhihu_content_url_removes_tracking_parameters_only() -> None:
    assert zhihu_service.normalize_zhihu_content_url(
        "https://www.zhihu.com/question/123/answer/456?foo=bar&utm_source=2cc8fff&utm_medium=openapi_platform#content"
    ) == "https://www.zhihu.com/question/123/answer/456?foo=bar#content"


@pytest.mark.asyncio
async def test_zhihu_global_search_uses_official_api_and_preserves_content_type(monkeypatch) -> None:
    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "test-secret")

    class FakeResponse:
        status_code = 200
        is_error = False

        def json(self):
            return {
                "Code": 0,
                "Message": "success",
                "Data": {
                    "HasMore": True,
                    "Items": [
                        {
                            "Title": "全网内容",
                            "ContentType": "Article",
                            "ContentID": "article-1",
                            "ContentText": "摘要<em>内容</em>",
                            "Url": "https://zhuanlan.zhihu.com/p/1?utm_medium=openapi_platform&utm_source=source",
                            "CommentCount": 2,
                            "VoteUpCount": 8,
                            "AuthorName": "作者",
                            "AuthorAvatar": "https://example.com/avatar.jpg",
                            "AuthorBadge": "",
                            "AuthorBadgeText": "",
                            "EditTime": 1748355858,
                            "CommentInfoList": [{"Content": "精选评论"}],
                            "AuthorityLevel": "2",
                        }
                    ],
                },
            }

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] > 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, *, params, headers):
            assert url == "https://developer.zhihu.com/api/v1/content/global_search"
            assert params == {
                "Query": "人工智能",
                "Count": 5,
                "SearchDB": "realtime",
                "Filter": 'host=="example.com"',
            }
            assert headers["Authorization"] == "Bearer test-secret"
            return FakeResponse()

    monkeypatch.setattr(zhihu_service.httpx, "AsyncClient", FakeClient)

    result = await zhihu_service.search_zhihu_global(
        "人工智能",
        "test-agent",
        count=5,
        filter_expression='host=="example.com"',
        search_db="realtime",
    )

    assert result["has_more"] is True
    assert result["items"][0]["content_type"] == "Article"
    assert result["items"][0]["excerpt"] == "摘要 内容"
    assert result["items"][0]["url"] == "https://zhuanlan.zhihu.com/p/1"


@pytest.mark.asyncio
async def test_web_search_keeps_duckduckgo_and_adds_zhihu_results(monkeypatch) -> None:
    import importlib

    web_search_module = importlib.import_module("app.plugins.tools.builtin.web_search")

    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "test-secret")
    monkeypatch.setattr(
        web_search_module,
        "_duckduckgo_search",
        SimpleNamespace(ainvoke=AsyncMock(return_value="DuckDuckGo 结果")),
    )
    monkeypatch.setattr(
        web_search_module,
        "search_zhihu_global",
        AsyncMock(
            return_value={
                "items": [
                    {
                        "title": "知乎结果",
                        "content_type": "Answer",
                        "excerpt": "知乎摘要",
                        "author_name": "作者",
                        "url": "https://www.zhihu.com/answer/1",
                    }
                ],
                "has_more": False,
            }
        ),
    )

    from app.plugins.tools.builtin.web_search import web_search

    result = await web_search.ainvoke({"query": "人工智能", "count": 5})

    assert "DuckDuckGo 结果" in result
    assert "知乎结果" in result
    assert "https://www.zhihu.com/answer/1" in result
