from __future__ import annotations

import os

from pydantic import BaseModel

from ...domain.dto import LLMMessage, LLMRequest, StructuredResult
from ...infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ...services.hotlist_service import fetch_hotlist


class DeepSeekLLMAdapter:
    """将 DeepSeekAnswerGenerator 适配为 LLMClientPort。"""

    def __init__(self) -> None:
        self._gen = DeepSeekAnswerGenerator()

    async def refine(self, instruction: str, current_answer: str) -> str:
        prompt = "\n".join([
            "请严格按照用户指令修改以下回答。",
            "只改动用户指定的部分，其余内容保持原样，不要自行发挥。",
            "",
            f"用户指令：{instruction}",
            "",
            "当前回答：",
            current_answer,
        ])
        return await self._gen.call_raw(
            system="你是专业的内容编辑助手。",
            user=prompt,
        )

    async def analyze(self, system_prompt: str, user_prompt: str) -> str:
        return await self._gen.call_raw(system=system_prompt, user=user_prompt)

    async def generate_structured(
        self,
        schema: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        retries: int = 1,
    ) -> StructuredResult:
        """公共结构化输出入口（roadmap R1）；三级降级，不抛异常。

        消费方拿到 StructuredResult 后，把 method_used/attempts/degradation_reason
        审计到各自 AIOperation.model_parameters。
        """
        from ...infrastructure.llm.registry import llm_provider_registry
        from ...infrastructure.llm.structured import generate_structured as _run

        provider = llm_provider_registry.get("deepseek")
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            temperature=0.1,
            max_tokens=4096,
        )
        return await _run(
            provider=provider,
            request=request,
            schema=schema,
            structured_methods=getattr(provider, "structured_methods", None),
            retries=retries,
        )


class HotlistServiceAdapter:
    """将 hotlist_service 适配为 HotlistServicePort。"""

    async def fetch(self, limit: int) -> list[dict]:
        response = await fetch_hotlist(limit=limit)
        return [item.model_dump(by_alias=True) for item in response.items]
