"""Writing-specific LLM operations expressed only through the shared gateway port."""

from __future__ import annotations

from pydantic import BaseModel

from app.shared.llm.dto import (
    LLMMessage,
    LLMRequest,
    StructuredLLMRequest,
    StructuredMethod,
)
from app.shared.llm.port import LLMGatewayPort


class WritingLLM:
    def __init__(self, gateway: LLMGatewayPort) -> None:
        self._gateway = gateway

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        response = await self._gateway.generate(
            purpose="writing.analysis",
            request=LLMRequest(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        )
        return response.content.strip()

    async def refine(self, instruction: str, current_answer: str) -> str:
        return await self.analyze(
            "你是专业的内容编辑助手。",
            "\n".join(
                [
                    "请严格按照用户指令修改以下回答。",
                    "只改动用户指定的部分，其余内容保持原样，不要自行发挥。",
                    "",
                    f"用户指令：{instruction}",
                    "",
                    "当前回答：",
                    current_answer,
                ]
            ),
        )

    async def generate_structured(
        self,
        schema: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        retries: int = 1,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        structured_methods: tuple[StructuredMethod, ...] | None = None,
    ):
        return await self._gateway.generate_structured(
            purpose="writing.review",
            request=StructuredLLMRequest(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                schema=schema,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=retries,
                structured_methods=structured_methods,
            ),
        )


def get_writing_llm() -> WritingLLM:
    from app.bootstrap.container import get_llm_gateway

    return WritingLLM(get_llm_gateway())
