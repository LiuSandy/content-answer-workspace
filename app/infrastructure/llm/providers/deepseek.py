"""DeepSeek LLM Provider；实现 domain.ports.LLMProvider 协议。"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from ....domain.dto import LLMMessage, LLMRequest, LLMResponse, LLMStreamEvent


class DeepSeekProvider:
    """DeepSeek (OpenAI 兼容) LLM Provider。

    实现 domain.ports.LLMProvider 协议（使用 Protocol，无需 isinstance 检查）。
    Agent 和 Workflow 只依赖此类，不引用 DeepSeek SDK 或专有响应类型。
    """

    key: str = "deepseek"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._custom_api_key = api_key
        self._custom_base_url = base_url
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            api_key = self._custom_api_key or os.getenv("DEEPSEEK_API_KEY", "")
            base_url = (
                (self._custom_base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
                .strip()
                .rstrip("/")
            )
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )
        return self._client

    def _to_openai_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """同步生成完整回复。"""
        client = self._get_client()
        resp = await client.chat.completions.create(
            model=request.model,
            messages=self._to_openai_messages(request.messages),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False,
            **(request.extra or {}),
        )
        choice = resp.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=resp.usage.prompt_tokens if resp.usage else None,
            output_tokens=resp.usage.completion_tokens if resp.usage else None,
            model=resp.model,
            finish_reason=choice.finish_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """流式生成回复；每个 chunk 产生一个 LLMStreamEvent。"""
        client = self._get_client()
        stream = await client.chat.completions.create(
            model=request.model,
            messages=self._to_openai_messages(request.messages),
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
            **(request.extra or {}),
        )
        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            delta = choice.delta.content if choice and choice.delta else ""
            finish_reason = choice.finish_reason if choice else None
            # 最后一个 chunk 可能携带 usage 信息
            usage = getattr(chunk, "usage", None)
            yield LLMStreamEvent(
                delta=delta or "",
                finish_reason=finish_reason,
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
            )
