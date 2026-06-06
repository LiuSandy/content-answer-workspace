from __future__ import annotations

from typing import Any

from ..core.config import DEFAULT_PLATFORM, get_default_topics, get_workflow_config, load_env_file
from ..infrastructure.collectors.factory import CollectorFactory
from ..models import QuestionItem, RegeneratePayload, RunPayload, SessionPayload, Topic, WorkflowResult
from ..services.answer_service import generate_answer
from ..services.zhihu_service import get_topic_preview, unique_by


def normalize_platform(value: str | None) -> str:
    """规范化平台标识；这样前端不传 platform 时仍能默认走 zhihu，未来扩展也有统一入口。"""

    return (value or DEFAULT_PLATFORM).strip().lower() or DEFAULT_PLATFORM


def normalize_topics(raw_topics: list[Topic] | list[dict[str, Any]] | None) -> list[Topic]:
    """规范化前端传入主题；这样工作流能同时接受 Pydantic 模型和原始字典并补齐扩展词。"""

    if raw_topics:
        return [get_topic_preview(Topic.model_validate(topic)) for topic in raw_topics]
    return [get_topic_preview(topic) for topic in get_default_topics()]


class WorkflowService:
    """编排采集和回答生成用例；这样 API 层保持轻薄，平台策略和模型调用由应用层统一调度。"""

    async def collect(self, payload: RunPayload | dict[str, Any] | None = None) -> WorkflowResult:
        """执行内容采集流程；这样平台选择、主题解析、去重和数量裁剪集中在一个用例里。"""

        load_env_file()
        options = self._to_options(payload)
        platform = normalize_platform(options.get("platform"))
        config = get_workflow_config({**options, "platform": platform})
        topics = normalize_topics(options.get("topics"))
        collector = CollectorFactory.create(platform)
        items = await collector.collect(topics, config)
        deduplicated = unique_by(items, lambda item: f"{item.platform}:{item.topic}:{item.id}")[: config.max_push_count]
        if not deduplicated:
            raise ValueError("No matching questions fetched")
        return WorkflowResult(platform=platform, config=config, topics=topics, items=deduplicated)

    async def generate_one(self, payload: RegeneratePayload) -> str:
        """为前端指定的单个问题生成回答；这样单条生成能复用统一的平台和提示词配置解析。"""

        load_env_file()
        platform = normalize_platform(payload.platform or payload.item.platform)
        item = payload.item.model_copy(update={"platform": platform})
        config = get_workflow_config(
            {
                "platform": platform,
                "answerStyle": payload.answer_style,
                "systemPrompt": payload.system_prompt,
            }
        )
        return await generate_answer(
            item,
            payload.answer_style or config.answer_style,
            config.cta_text,
            payload.system_prompt or config.system_prompt,
        )

    async def generate_many(self, payload: SessionPayload) -> list[QuestionItem]:
        """批量生成前端提交问题的回答；这样批量入口不会重新采集，只处理用户确认的问题列表。"""

        load_env_file()
        platform = normalize_platform(payload.platform)
        config = get_workflow_config(
            {
                "platform": platform,
                "answerStyle": payload.answer_style,
                "systemPrompt": payload.system_prompt,
            }
        )
        items: list[QuestionItem] = []
        for item in payload.items:
            normalized_item = item.model_copy(update={"platform": normalize_platform(item.platform or platform)})
            answer = await generate_answer(
                normalized_item,
                payload.answer_style or config.answer_style,
                config.cta_text,
                payload.system_prompt or config.system_prompt,
            )
            items.append(normalized_item.model_copy(update={"answer": answer}))
        return items

    async def run(self, payload: RunPayload | dict[str, Any] | None = None) -> WorkflowResult:
        """执行采集后可选生成的完整流程；这样 CLI 和旧接口可以复用新工作流编排。"""

        collected = await self.collect(payload)
        options = self._to_options(payload)
        if options.get("skipAnswerGeneration") is True or collected.config.skip_answer_generation:
            return collected

        answered_items: list[QuestionItem] = []
        for item in collected.items:
            answer = await generate_answer(
                item,
                collected.config.answer_style,
                collected.config.cta_text,
                collected.config.system_prompt,
            )
            answered_items.append(item.model_copy(update={"answer": answer}))
        return collected.model_copy(update={"items": answered_items})

    def _to_options(self, payload: RunPayload | dict[str, Any] | None) -> dict[str, Any]:
        """把请求载荷转换成普通字典；这样旧字典调用和新 Pydantic 请求能走同一套逻辑。"""

        if payload is None:
            return {}
        if isinstance(payload, RunPayload):
            return payload.model_dump(by_alias=True)
        return dict(payload)
