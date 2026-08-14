"""Provider-agnostic answer generation and editing workflows."""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.api.schemas.workflow import QuestionItem
from app.config.runtime import get_required_env
from app.contracts.dto import LLMMessage, LLMRequest
from app.contracts.ports import AnswerGeneratorPort, LLMProvider
from app.infrastructure.llm.registry import llm_provider_registry
from app.prompts.registry import prompt_registry


class AnswerGenerationService(AnswerGeneratorPort):
    """Compose business prompts and delegate model I/O to an LLMProvider."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    def _get_provider(self) -> LLMProvider:
        return self._provider or llm_provider_registry.get_default()

    def _request(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMRequest:
        return LLMRequest(
            messages=messages,
            model=model or get_required_env("DEEPSEEK_MODEL"),
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
        response = await self._get_provider().generate(request)
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
        async for event in self._get_provider().stream(request):
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
        response = await self._get_provider().generate(
            self._render_polish_request(item, current_answer)
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
        async for event in self._get_provider().stream(request):
            if event.delta:
                yield event.delta

    async def call_raw(self, system: str, user: str) -> str:
        request = self._request(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=user),
            ]
        )
        response = await self._get_provider().generate(request)
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
        async for event in self._get_provider().stream(request):
            if event.delta:
                yield event.delta

    async def chat(self, messages: list[dict[str, str]]) -> str:
        request = self._request([LLMMessage.model_validate(message) for message in messages])
        response = await self._get_provider().generate(request)
        content = response.content.strip()
        if not content:
            raise ValueError("LLM provider returned empty chat content")
        return content
