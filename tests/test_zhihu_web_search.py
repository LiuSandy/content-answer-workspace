from __future__ import annotations

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
