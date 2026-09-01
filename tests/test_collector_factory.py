from __future__ import annotations

import pytest

from app.plugins.sources.factory import CollectorFactory
from app.plugins.sources.zhihu_collector import ZhihuCollector


@pytest.mark.parametrize("source", ["auto", "web", "official"])
def test_zhihu_collection_uses_zhihu_api_collector(source: str):
    collector = CollectorFactory.create("zhihu", source=source)

    assert isinstance(collector, ZhihuCollector)
