from __future__ import annotations

import json
import re

from app.shared.llm.dto import LLMMessage, LLMRequest
from app.shared.llm.port import LLMGatewayPort


class LLMExtractor:
    """调用 LLM 从清洗后的文本中提取结构化条目。"""

    def __init__(self, gateway: LLMGatewayPort | None = None) -> None:
        self._gateway = gateway

    def _get_gateway(self) -> LLMGatewayPort:
        if self._gateway is None:
            from app.bootstrap.container import get_llm_gateway

            self._gateway = get_llm_gateway()
        return self._gateway

    async def extract(self, text: str, prompt: str) -> list[dict[str, str]]:
        system = "你只返回 JSON 数组，不要任何额外说明。数组为空时返回 []。"
        user = f"{prompt}\n\n---\n{text}"
        response = await self._get_gateway().generate(
            purpose="acquisition.extract",
            request=LLMRequest(
                messages=[
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=user),
                ],
            ),
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
