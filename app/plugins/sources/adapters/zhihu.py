"""Zhihu Content Source 适配器；实现 domain.ports.ContentSource 协议。"""
from __future__ import annotations

from app.shared.dto import (
    SourceItemDTO,
    ParseUrlRequest,
    CollectionRequest,
    ToolContext,
)
from app.modules.acquisition.domain.workflow import QuestionItem, Topic
from app.platform.config.runtime import get_workflow_config
from app.modules.acquisition.application.zhihu import fetch_zhihu_question_by_url
from app.plugins.sources.zhihu_collector import ZhihuCollector


def _question_item_to_dto(item: QuestionItem) -> SourceItemDTO:
    return SourceItemDTO(
        external_id=item.id,
        platform="zhihu",
        url=item.url,
        title=item.title,
        content=item.detail or item.excerpt or None,
        author=None,
        summary=item.excerpt or None,
        metrics={"answer_count": item.answer_count},
        published_at=None,
        raw_metadata={
            "updated_time": item.updated_time,
            "content_mode": item.content_mode,
        } if item.updated_time else {"content_mode": item.content_mode},
    )


class ZhihuSource:
    """知乎内容源适配器。"""

    key: str = "zhihu"

    @property
    def capabilities(self) -> set[str]:
        return {"parse_url", "collect"}

    def can_handle_url(self, url: str) -> bool:
        # 能够处理含有 zhihu.com 且匹配 question 的链接
        return "zhihu.com" in url.lower() and "question" in url.lower()

    async def parse_url(
        self, request: ParseUrlRequest, context: ToolContext
    ) -> SourceItemDTO:
        # 获取默认 workflow 配置
        config = get_workflow_config()
        # 调用 zhihu_service 中的 fetch_zhihu_question_by_url
        item = await fetch_zhihu_question_by_url(
            url=request.url,
            user_agent=config.user_agent,
            topic_name="链接导入",
        )
        return _question_item_to_dto(item)

    async def collect(
        self, request: CollectionRequest, context: ToolContext
    ) -> list[SourceItemDTO]:
        # 创建 Topic 对象
        topic = Topic(
            id="temp_topic",
            name=request.query,
            keywords=[request.query],
        )

        config = get_workflow_config({
            "platform": "zhihu",
            "maxPushCount": request.max_results,
        })

        collector = ZhihuCollector()
        items = await collector.collect([topic], config)
        return [_question_item_to_dto(item) for item in items]
