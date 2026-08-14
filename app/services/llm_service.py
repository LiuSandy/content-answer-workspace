from __future__ import annotations

import os

from pydantic import BaseModel

from app.contracts.dto import LLMMessage, LLMRequest, StructuredResult
from app.infrastructure.llm.clients.deepseek_client import DeepSeekAnswerGenerator


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
        from app.infrastructure.llm.registry import llm_provider_registry
        from app.infrastructure.llm.structured_output import generate_structured as _run

        provider = llm_provider_registry.get("deepseek")
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ],
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
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
