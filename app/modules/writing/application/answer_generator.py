"""Provider-agnostic answer generation and editing workflows."""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.shared.content import QuestionItem
from app.platform.prompts.registry import prompt_registry
from app.shared.llm.dto import LLMMessage, LLMRequest
from app.shared.llm.port import LLMGatewayPort


class AnswerGenerationService:
    """Compose business prompts and delegate model I/O to the application gateway."""

    def __init__(self, gateway: LLMGatewayPort | None = None) -> None:
        self._gateway = gateway

    def _get_gateway(self) -> LLMGatewayPort:
        if self._gateway is None:
            from app.bootstrap.container import get_llm_gateway

            self._gateway = get_llm_gateway()
        return self._gateway

    def _request(
        self,
        messages: list[object],
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMRequest:
        return LLMRequest(
            messages=[
                message
                if isinstance(message, LLMMessage)
                else LLMMessage.model_validate(message.model_dump())
                for message in messages
            ],
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _render_answer_request(self, item: QuestionItem, cta_text: str) -> LLMRequest:
        rendered = prompt_registry.render("writing.answer_generate")
        user_rendered = prompt_registry.render(
            "writing.user_generate",
            title=item.title,
            content=item.excerpt or item.detail or "",
            content_mode=item.content_mode,
        )
        messages = [*rendered.messages, *user_rendered.messages]
        if cta_text and cta_text.strip():
            messages.append(LLMMessage(role="user", content=f"\n\n结尾引流文案：{cta_text}"))
        return self._request(
            messages,
            provider=rendered.provider,
            model=rendered.model,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
        )

    def _render_polish_request(self, item: QuestionItem, current_answer: str) -> LLMRequest:
        rendered = prompt_registry.render("writing.answer_rewrite")
        user_rendered = prompt_registry.render(
            "writing.user_rewrite",
            title=item.title,
            current_answer=current_answer,
            instruction="润色改写语言表达，消除 AI 腔，让行文更自然简洁，保留原有观点。",
            content_mode=item.content_mode,
        )
        return self._request(
            [*rendered.messages, *user_rendered.messages],
            provider=rendered.provider,
            model=rendered.model,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
        )

    async def generate_answer(
        self,
        item: QuestionItem,
        answer_style: str = "",
        cta_text: str = "",
        system_prompt: str = "",
        generation_prompt: str = "",
        content_constraint: str | None = None,
    ) -> str:
        request = self._render_answer_request(item, cta_text)
        response = await self._get_gateway().generate(
            purpose="writing.generate", request=request
        )
        content = response.content.strip()
        if not content:
            raise ValueError("LLM provider returned empty answer content")
        return content

    async def generate_answer_stream(
        self,
        item: QuestionItem,
        answer_style: str = "",
        cta_text: str = "",
        system_prompt: str = "",
        generation_prompt: str = "",
        content_constraint: str | None = None,
    ) -> AsyncIterator[str]:
        request = self._render_answer_request(item, cta_text)
        async for event in self._get_gateway().stream(
            purpose="writing.generate", request=request
        ):
            if event.delta:
                yield event.delta

    async def polish_answer(
        self,
        item: QuestionItem,
        current_answer: str,
        answer_style: str = "",
        cta_text: str = "",
        system_prompt: str = "",
        generation_prompt: str = "",
        content_constraint: str | None = None,
    ) -> str:
        response = await self._get_gateway().generate(
            purpose="writing.rewrite",
            request=self._render_polish_request(item, current_answer),
        )
        content = response.content.strip()
        if not content:
            raise ValueError("LLM provider returned empty polish content")
        return content

    async def polish_answer_stream(
        self,
        item: QuestionItem,
        current_answer: str,
        answer_style: str = "",
        cta_text: str = "",
        system_prompt: str = "",
        generation_prompt: str = "",
        content_constraint: str | None = None,
    ) -> AsyncIterator[str]:
        request = self._render_polish_request(item, current_answer)
        async for event in self._get_gateway().stream(
            purpose="writing.rewrite", request=request
        ):
            if event.delta:
                yield event.delta

    async def call_raw(self, system: str, user: str) -> str:
        request = self._request(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=user),
            ]
        )
        response = await self._get_gateway().generate(
            purpose="writing.analysis", request=request
        )
        content = response.content.strip()
        if not content:
            raise ValueError("LLM provider returned empty content")
        return content

    async def call_raw_stream(self, system: str, user: str) -> AsyncIterator[str]:
        request = self._request(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=user),
            ]
        )
        async for event in self._get_gateway().stream(
            purpose="writing.analysis", request=request
        ):
            if event.delta:
                yield event.delta

    async def chat(self, messages: list[dict[str, str]]) -> str:
        request = self._request([LLMMessage.model_validate(message) for message in messages])
        response = await self._get_gateway().generate(
            purpose="writing.chat", request=request
        )
        content = response.content.strip()
        if not content:
            raise ValueError("LLM provider returned empty chat content")
        return content
