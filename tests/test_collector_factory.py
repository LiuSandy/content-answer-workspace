from __future__ import annotations

import pytest

from app.plugins.sources.factory import CollectorFactory
from app.plugins.sources.zhihu_collector import ZhihuCollector


@pytest.mark.parametrize("source", ["auto", "web"])
def test_zhihu_collection_uses_web_collector(source: str):
    collector = CollectorFactory.create("zhihu", source=source)

    assert isinstance(collector, ZhihuCollector)


def test_zhihu_official_source_is_not_supported():
    with pytest.raises(ValueError, match="official.*not supported"):
        CollectorFactory.create("zhihu", source="official")
