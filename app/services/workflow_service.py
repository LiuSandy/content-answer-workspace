from __future__ import annotations

from typing import Any

from app.config.runtime import DEFAULT_PLATFORM, get_default_topics, get_workflow_config, load_env_file
from ..infrastructure.collectors.factory import CollectorFactory
from app.api.schemas.workflow import ParseQuestionUrlPayload, PolishPayload, QuestionItem, RegeneratePayload, RunPayload, SessionPayload, Topic, WorkflowResult
from ..services.answer_service import generate_answer, generate_answer_with_images, polish_answer
from ..services.topic_expansion_service import expand_topic_for_collection
from ..services.zhihu_service import fetch_zhihu_question_by_url, get_topic_preview, unique_by


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
        source = str(options.get("source") or "auto").strip().lower()
        config = get_workflow_config({**options, "platform": platform, "source": source})
        topics = normalize_topics(options.get("topics"))
        expanded_topics = [await expand_topic_for_collection(topic) for topic in topics]
        collector = CollectorFactory.create(platform, source=source)
        items = await collector.collect(expanded_topics, config)
        deduplicated = unique_by(items, lambda item: f"{item.platform}:{item.topic}:{item.id}")[: config.max_push_count]
        if not deduplicated:
            raise ValueError("No matching questions fetched")
        return WorkflowResult(platform=platform, config=config, topics=expanded_topics, items=deduplicated)

    async def generate_one(self, payload: RegeneratePayload) -> QuestionItem:
        """为前端指定的单个问题生成回答和配图；这样单条生成能一次返回完整可展示的问题对象。"""

        load_env_file()
        platform = normalize_platform(payload.platform or payload.item.platform)
        item = payload.item.model_copy(update={"platform": platform})
        config = get_workflow_config(
            {
                "platform": platform,
                "answerStyle": payload.answer_style,
                "systemPrompt": payload.system_prompt,
                "generationPrompt": payload.generation_prompt,
            }
        )
        answer, image_payload = await generate_answer_with_images(
            item,
            payload.answer_style or config.answer_style,
            config.cta_text,
            payload.system_prompt or config.system_prompt,
            payload.generation_prompt or config.generation_prompt,
            payload.content_constraint or None,
        )
        return item.model_copy(
            update={
                "answer": answer,
                "images": image_payload.get("images", []),
                "image_prompts": image_payload.get("imagePrompts", []),
            }
        )

    async def polish_one(self, payload: PolishPayload) -> QuestionItem:
        """对单个问题的现有回答进行润色；这样用户编辑的草稿可以通过 AI 改善表达而不重新生成。"""

        load_env_file()
        platform = normalize_platform(payload.platform or payload.item.platform)
        item = payload.item.model_copy(update={"platform": platform})
        config = get_workflow_config(
            {
                "platform": platform,
                "answerStyle": payload.answer_style,
                "systemPrompt": payload.system_prompt,
                "generationPrompt": payload.generation_prompt,
            }
        )
        polished = await polish_answer(
            item,
            payload.current_answer,
            payload.answer_style or config.answer_style,
            config.cta_text,
            payload.system_prompt or config.system_prompt,
            payload.generation_prompt or config.generation_prompt,
            payload.content_constraint or None,
        )
        return item.model_copy(update={"answer": polished})

    async def parse_question_url(self, payload: ParseQuestionUrlPayload) -> QuestionItem:
        """按问题链接导入单个题目；这样用户可以跳过检索，直接把指定问题送入现有回答工作流。"""

        load_env_file()
        platform = normalize_platform(payload.platform)
        if platform != "zhihu":
            raise ValueError(f"当前仅支持知乎问题链接导入，暂不支持平台：{platform}")

        config = get_workflow_config({"platform": platform})
        item = await fetch_zhihu_question_by_url(payload.url, config.user_agent, "链接导入")
        return item.model_copy(update={"platform": platform})

    async def generate_many(self, payload: SessionPayload) -> list[QuestionItem]:
        """批量生成前端提交问题的回答；这样批量入口不会重新采集，只处理用户确认的问题列表。"""

        load_env_file()
        platform = normalize_platform(payload.platform)
        config = get_workflow_config(
            {
                "platform": platform,
                "answerStyle": payload.answer_style,
                "systemPrompt": payload.system_prompt,
                "generationPrompt": payload.generation_prompt,
            }
        )
        items: list[QuestionItem] = []
        for item in payload.items:
            normalized_item = item.model_copy(update={"platform": normalize_platform(item.platform or platform)})
            answer, image_payload = await generate_answer_with_images(
                normalized_item,
                payload.answer_style or config.answer_style,
                config.cta_text,
                payload.system_prompt or config.system_prompt,
                payload.generation_prompt or config.generation_prompt,
                payload.content_constraint or None,
            )
            items.append(
                normalized_item.model_copy(
                    update={
                        "answer": answer,
                        "images": image_payload.get("images", []),
                        "image_prompts": image_payload.get("imagePrompts", []),
                    }
                )
            )
        return items

    async def run(self, payload: RunPayload | dict[str, Any] | None = None) -> WorkflowResult:
        """执行采集后可选生成的完整流程；这样 CLI 和旧接口可以复用新工作流编排。"""

        collected = await self.collect(payload)
        options = self._to_options(payload)
        if options.get("skipAnswerGeneration") is True or collected.config.skip_answer_generation:
            return collected

        answered_items: list[QuestionItem] = []
        for item in collected.items:
            answer, image_payload = await generate_answer_with_images(
                item,
                collected.config.answer_style,
                collected.config.cta_text,
                collected.topics[0].system_prompt if collected.topics else collected.config.system_prompt,
                collected.config.generation_prompt,
            )
            answered_items.append(
                item.model_copy(
                    update={
                        "answer": answer,
                        "images": image_payload.get("images", []),
                        "image_prompts": image_payload.get("imagePrompts", []),
                    }
                )
            )
        return collected.model_copy(update={"items": answered_items})

    def _to_options(self, payload: RunPayload | dict[str, Any] | None) -> dict[str, Any]:
        """把请求载荷转换成普通字典；这样旧字典调用和新 Pydantic 请求能走同一套逻辑。"""

        if payload is None:
            return {}
        if isinstance(payload, RunPayload):
            return payload.model_dump(by_alias=True)
        return dict(payload)
