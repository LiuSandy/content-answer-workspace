from __future__ import annotations

import json
import re

from app.infrastructure.llm.clients.deepseek_client import DeepSeekAnswerGenerator


class LLMExtractor:
    """调用 LLM 从清洗后的文本中提取结构化条目。"""

    def __init__(self) -> None:
        self._generator = DeepSeekAnswerGenerator()

    async def extract(self, text: str, prompt: str) -> list[dict[str, str]]:
        system = "你只返回 JSON 数组，不要任何额外说明。数组为空时返回 []。"
        user = f"{prompt}\n\n---\n{text}"
        raw = await self._generator.call_raw(system, user)
        return self._parse(raw)

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
