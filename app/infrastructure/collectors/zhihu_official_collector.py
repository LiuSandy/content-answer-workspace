from __future__ import annotations

import logging
import re
from typing import Any, Sequence

import httpx

from ...domain.ports import CollectorPort
from ...models import QuestionItem, Topic, WorkflowConfig
from ...services.zhihu_service import clean_text, get_topic_retrieval_keywords, get_zhihu_question_web_url, unique_by
from ..zhihu.official_client import ZhihuOfficialClient

logger = logging.getLogger(__name__)


class ZhihuOfficialCollector(CollectorPort):
    """使用知乎官方搜索 API 采集问题；这样采集不依赖 cookie 和逆向签名，稳定性由官方接口保证。"""

    platform = "zhihu"

    def __init__(self) -> None:
        self._client = ZhihuOfficialClient()

    async def collect(self, topics: Sequence[Topic], config: WorkflowConfig) -> list[QuestionItem]:
        """按主题列表调用官方搜索采集问题；这样扩词和去重逻辑与现有爬取流程保持一致。"""
        items: list[QuestionItem] = []
        for topic in topics:
            topic_items = await self._collect_for_topic(topic, config.max_push_count)
            items.extend(item.model_copy(update={"platform": self.platform}) for item in topic_items)
        return items

    async def _collect_for_topic(self, topic: Topic, limit: int) -> list[QuestionItem]:
        """对单个主题的每个检索词调用官方搜索并汇总；这样多关键词结果经去重后覆盖面更广。"""
        keywords = get_topic_retrieval_keywords(topic)
        aggregated: list[QuestionItem] = []
        for keyword in keywords:
            try:
                raw = await self._client.search(keyword, count=10)
                items = self._map_results(raw, topic.name)
                aggregated.extend(items)
            except ValueError:
                # 凭据缺失等配置错误应向上传播，不静默吞掉
                raise
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                # 单个关键词网络/API 错误时跳过，继续其余关键词
                logger.warning("官方搜索关键词 %r 失败，跳过：%s", keyword, exc)
                continue
        return unique_by(aggregated, lambda item: item.id)[:limit]

    def _map_results(self, raw: dict[str, Any], topic_name: str) -> list[QuestionItem]:
        """将官方搜索响应映射到内部 QuestionItem；这样官方字段变化只需修改此处的映射逻辑。"""
        results: list[QuestionItem] = []

        # 官方 API 响应格式: {"Code": 0, "Data": {"Items": [...]}}
        data = raw.get("Data") or raw.get("data") or {}
        entries = data.get("Items") or data.get("items") or []
        if not isinstance(entries, list):
            return results

        for entry in entries:
            item = self._map_entry(entry, topic_name)
            if item is not None:
                results.append(item)

        return results

    def _map_entry(self, entry: dict[str, Any], topic_name: str) -> QuestionItem | None:
        """将单条官方搜索结果映射为 QuestionItem；这样 Answer/Question 混合返回时仍能归一处理。"""
        if not isinstance(entry, dict):
            return None

        url = entry.get("Url") or entry.get("url") or ""

        # 从 URL 中提取问题 ID（URL 格式: /question/123 或 /question/123/answer/456）
        question_id = self._extract_question_id(url)
        if not question_id:
            return None

        # 确保是问题页 URL，截掉 /answer/... 部分
        question_url = get_zhihu_question_web_url(question_id)

        title = clean_text(entry.get("Title") or entry.get("title") or "")
        # 标题末尾可能带 " - 知乎"，去掉
        if title.endswith(" - 知乎"):
            title = title[: -len(" - 知乎")].strip()
        if not title:
            return None

        excerpt = clean_text(entry.get("ContentText") or entry.get("excerpt") or "")
        vote_up = int(entry.get("VoteUpCount") or 0)

        return QuestionItem(
            id=question_id,
            platform=self.platform,
            title=title,
            url=question_url,
            answerCount=vote_up,
            excerpt=excerpt,
            detail="",
            topic=topic_name,
        )

    def _extract_question_id(self, url: str) -> str | None:
        """从知乎 URL 中提取问题 ID；支持 /question/123 和 /question/123/answer/456 两种格式。"""
        match = re.search(r"/question/(\d+)", url)
        return match.group(1) if match else None
