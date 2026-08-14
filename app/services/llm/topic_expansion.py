"""Provider-agnostic topic keyword expansion."""
from __future__ import annotations

import json
import os
import re

from app.api.schemas.workflow import Topic
from app.config.runtime import get_required_env
from app.contracts.dto import LLMMessage, LLMRequest
from app.contracts.ports import LLMProvider, TopicExpanderPort
from app.infrastructure.llm.registry import llm_provider_registry


class TopicExpansionService(TopicExpanderPort):
    """Build the expansion prompt and parse normalized keyword output."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    def _get_provider(self) -> LLMProvider:
        return self._provider or llm_provider_registry.get_default()

    async def expand_topic(self, topic: Topic, limit: int = 6) -> list[str]:
        model = (
            os.getenv("DEEPSEEK_TOPIC_EXPANSION_MODEL", "").strip()
            or get_required_env("DEEPSEEK_MODEL")
        )
        seed_keywords = "、".join(
            keyword for keyword in topic.keywords if keyword.strip()
        ) or "无"
        prompt = "\n".join(
            [
                "你现在是中文内容检索助手。",
                "任务：根据给定主题，补充一批适合社交平台检索的相近主题词或搜索关键词。",
                "要求：",
                f"1. 返回 4 到 {max(limit, 4)} 个中文关键词或短语。",
                "2. 关键词要贴近用户在知乎真实会搜索的问题主题，不要写解释。",
                "3. 不要返回序号、标题、Markdown 代码块。",
                "4. 允许包含少量英文术语，但整体以中文检索词为主。",
                '5. 输出必须是 JSON，对象格式固定为 {"keywords": ["词1", "词2"]}。',
                "",
                f"主题名称：{topic.name}",
                f"已有关键词：{seed_keywords}",
            ]
        )
        response = await self._get_provider().generate(
            LLMRequest(
                model=model,
                messages=[
                    LLMMessage(role="system", content="你只返回 JSON，不要输出任何额外说明。"),
                    LLMMessage(role="user", content=prompt),
                ],
            )
        )
        keywords = self._parse_keywords(response.content, limit)
        if not keywords:
            raise ValueError(f"LLM provider returned empty topic keywords for topic: {topic.name}")
        return keywords

    def _parse_keywords(self, text: str, limit: int) -> list[str]:
        text = text.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = self._extract_json_fragment(text)

        if isinstance(payload, dict):
            raw_keywords = payload.get("keywords", [])
        elif isinstance(payload, list):
            raw_keywords = payload
        else:
            raw_keywords = []
        if not raw_keywords:
            raw_keywords = re.split(r"[\n,，、;；]+", text)

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_keyword in raw_keywords:
            keyword = str(raw_keyword).strip().strip("\"'[]")
            key = keyword.lower()
            if not keyword or key in seen:
                continue
            seen.add(key)
            normalized.append(keyword)
            if len(normalized) >= limit:
                break
        return normalized

    def _extract_json_fragment(self, text: str) -> dict[str, object] | list[object] | None:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
