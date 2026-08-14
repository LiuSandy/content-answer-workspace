from __future__ import annotations

import json
import re

from app.config.runtime import get_required_env
from app.contracts.dto import LLMMessage, LLMRequest
from app.contracts.ports import LLMProvider
from app.infrastructure.llm.registry import llm_provider_registry


class LLMExtractor:
    """调用 LLM 从清洗后的文本中提取结构化条目。"""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    def _get_provider(self) -> LLMProvider:
        return self._provider or llm_provider_registry.get_default()

    async def extract(self, text: str, prompt: str) -> list[dict[str, str]]:
        system = "你只返回 JSON 数组，不要任何额外说明。数组为空时返回 []。"
        user = f"{prompt}\n\n---\n{text}"
        response = await self._get_provider().generate(
            LLMRequest(
                model=get_required_env("DEEPSEEK_MODEL"),
                messages=[
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user),
                ],
            )
        )
        return self._parse(response.content)

    def _parse(self, raw: str) -> list[dict[str, str]]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = raw.rstrip("`").strip()
        try:
            result = json.loads(raw)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []
