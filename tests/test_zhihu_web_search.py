from __future__ import annotations

import pytest

from app.modules.acquisition.domain.workflow import Topic
from app.modules.acquisition.application import zhihu as zhihu_service


def test_extract_zhihu_search_items_from_rendered_html() -> None:
    html = """
    <html><body>
      <article><a href="https://www.zhihu.com/question/123">个人网站建设有哪些方案</a><p>摘要内容</p></article>
      <article><a href="/question/456">如何搭建个人网站</a><p>另一个摘要</p></article>
    </body></html>
    """

    items = zhihu_service.extract_zhihu_search_items_from_html(html, "个人网站", limit=10)

    assert [item.id for item in items] == ["123", "456"]
    assert items[0].url == "https://www.zhihu.com/question/123"
    assert items[0].excerpt == "摘要内容"


@pytest.mark.asyncio
async def test_search_zhihu_for_keyword_uses_rendered_search_page(monkeypatch) -> None:
    class FakeFetcher:
        def __init__(self, **kwargs):
            assert kwargs["cookie_domain"] == ".zhihu.com"

        async def fetch(self, url: str, headers: dict[str, str]) -> str:
            assert url.startswith("https://www.zhihu.com/search?type=content&q=")
            assert "api.zhihu" not in url
            assert "x-zse" not in str(headers).lower()
            return '<a href="/question/123">个人网站建设有哪些方案</a>'

    monkeypatch.setattr(zhihu_service, "PlaywrightFetcher", FakeFetcher)

    items = await zhihu_service.search_zhihu_for_keyword(
        Topic(id="personal-site", name="个人网站", keywords=[]),
        "个人网站",
        "test-agent",
        limit=10,
    )

    assert [item.id for item in items] == ["123"]
