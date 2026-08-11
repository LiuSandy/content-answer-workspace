"""回答生成工作流（roadmap R7：薄适配器，委托 WriterService）。"""
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ..application.writer_service import WriterRunCapture, run_writer_stream
from ..infrastructure.llm.registry import llm_provider_registry
from ..persistence.models.content import SourceItem
from ..prompts.composer import compose_writing_prompt
from ..prompts.registry import prompt_registry

logger = logging.getLogger("uvicorn")


async def generate_answer_workflow(
    session: AsyncSession,
    source_item_id: uuid.UUID,
    document_id: uuid.UUID,
    platform: str,
    title: str,
    content: str | None,
    expected_lock_version: int,
    capture: WriterRunCapture,
    style_rules: str | None = None,
    word_count: int = 1000,
    instruction: str | None = None,
    extra_context: str | None = None,
) -> AsyncIterator[str]:
    source_item = await session.get(SourceItem, source_item_id)
    content_mode = "answer"
    if source_item and source_item.raw_metadata:
        content_mode = source_item.raw_metadata.get("content_mode") or "answer"

    try:
        rendered = compose_writing_prompt(
            "writing.answer_generate",
            platform=platform,
            style_rules=style_rules,
            word_count=word_count,
        )
        user_rendered = prompt_registry.render(
            "writing.user_generate",
            title=title,
            content=content or "",
            content_mode=content_mode,
            instruction=instruction,
        )
        rendered.messages.extend(user_rendered.messages)
    except Exception as e:
        logger.error("Failed to render prompt for answer generation: %s", e)
        raise

    async for delta in run_writer_stream(
        session, "generate", document_id, rendered, expected_lock_version,
        platform=platform, extra_context=extra_context,
        defer_version=True, capture=capture,
    ):
        yield delta
