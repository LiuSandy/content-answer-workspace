from __future__ import annotations

from typing import Sequence

from ...domain.ports import CollectorPort
from ...models import QuestionItem, Topic, WorkflowConfig
from ...services.zhihu_service import fetch_zhihu_results_for_topic


class ZhihuCollector(CollectorPort):
    """实现知乎平台采集策略；这样知乎细节被限制在平台适配器内，工作流只看到统一采集接口。"""

    platform = "zhihu"

    async def collect(self, topics: Sequence[Topic], config: WorkflowConfig) -> list[QuestionItem]:
        """按主题采集知乎问题；这样当前默认平台能复用原有知乎解析逻辑并补齐平台标识。"""

        items: list[QuestionItem] = []
        for topic in topics:
            topic_items = await fetch_zhihu_results_for_topic(topic, config.user_agent)
            items.extend(item.model_copy(update={"platform": self.platform}) for item in topic_items)
        return items
