"""Xiaohongshu Content Source 适配器；实现 domain.ports.ContentSource 协议。"""
from __future__ import annotations

from app.shared.dto import (
    SourceItemDTO,
    ParseUrlRequest,
    CollectionRequest,
    ToolContext,
)
from app.shared.content import QuestionItem, Topic
from app.platform.config.runtime import get_workflow_config
from app.shared.errors import UnsupportedSourceError
from app.plugins.sources.xiaohongshu_collector import XiaohongshuCollector


def _question_item_to_dto(item: QuestionItem) -> SourceItemDTO:
    return SourceItemDTO(
        external_id=item.id,
        platform="xiaohongshu",
        url=item.url,
        title=item.title,
        content=item.detail or item.excerpt or None,
        author=None,
        summary=item.excerpt or None,
        metrics={},
        published_at=None,
        raw_metadata={"content_mode": item.content_mode} if item.content_mode else {},
    )


class XiaohongshuSource:
    """小红书内容源适配器。"""

    key: str = "xiaohongshu"

    @property
    def capabilities(self) -> set[str]:
        return {"collect"}

    def can_handle_url(self, url: str) -> bool:
        lower_url = url.lower()
        return "xiaohongshu.com" in lower_url or "xhs.link" in lower_url

    async def parse_url(
        self, request: ParseUrlRequest, context: ToolContext
    ) -> SourceItemDTO:
        raise UnsupportedSourceError("xiaohongshu does not support URL parsing")

    async def collect(
        self, request: CollectionRequest, context: ToolContext
    ) -> list[SourceItemDTO]:
        topic = Topic(
            id="temp_topic",
            name=request.query,
            keywords=[request.query],
        )

        config = get_workflow_config({
            "platform": "xiaohongshu",
            "maxPushCount": request.max_results,
        })

        collector = XiaohongshuCollector()
        items = await collector.collect([topic], config)
        return [_question_item_to_dto(item) for item in items]
