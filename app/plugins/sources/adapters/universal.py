"""Universal Content Source 适配器；实现 domain.ports.ContentSource 协议。"""
from __future__ import annotations

from app.shared.dto import (
    SourceItemDTO,
    ParseUrlRequest,
    CollectionRequest,
    ToolContext,
)
from app.shared.content import QuestionItem, Topic
from app.platform.config.runtime import get_workflow_config
from app.shared.errors import UnsupportedSourceError, ValidationError
from app.plugins.sources.platform_config_loader import PlatformConfigLoader
from app.plugins.sources.universal_collector import UniversalCollector


def _question_item_to_dto(item: QuestionItem, platform: str) -> SourceItemDTO:
    return SourceItemDTO(
        external_id=item.id,
        platform=platform,
        url=item.url,
        title=item.title,
        content=item.detail or item.excerpt or None,
        author=None,
        summary=item.excerpt or None,
        metrics={},
        published_at=None,
        raw_metadata={"content_mode": item.content_mode} if item.content_mode else {},
    )


class UniversalSource:
    """通用 YAML 配置内容源适配器。"""

    key: str = "universal"

    @property
    def capabilities(self) -> set[str]:
        return {"collect"}

    def can_handle_url(self, url: str) -> bool:
        # 统一由特定平台的适配器处理 url，通用适配器不支持 can_handle_url
        return False

    async def parse_url(
        self, request: ParseUrlRequest, context: ToolContext
    ) -> SourceItemDTO:
        raise UnsupportedSourceError("universal source does not support URL parsing")

    async def collect(
        self, request: CollectionRequest, context: ToolContext
    ) -> list[SourceItemDTO]:
        if not request.platform:
            raise ValidationError("platform is required for universal collection")

        platform_name = request.platform.strip().lower()
        yaml_config = PlatformConfigLoader.load(platform_name)
        if yaml_config is None:
            raise UnsupportedSourceError(f"YAML config not found for platform: {platform_name}")

        topic = Topic(
            id="temp_topic",
            name=request.query,
            keywords=[request.query],
        )

        config = get_workflow_config({
            "platform": platform_name,
            "maxPushCount": request.max_results,
        })

        collector = UniversalCollector(yaml_config)
        items = await collector.collect([topic], config)
        return [_question_item_to_dto(item, platform_name) for item in items]
