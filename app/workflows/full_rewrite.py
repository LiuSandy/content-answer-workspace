"""全文重写工作流（roadmap R7：薄适配器，委托 WriterService）。"""
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.document_service import DocumentService
from ..application.writer_service import run_writer_stream
from ..persistence.models.documents import AnswerDocument
from ..prompts.composer import compose_writing_prompt
from ..prompts.registry import prompt_registry

logger = logging.getLogger("uvicorn")


async def full_rewrite_workflow(
    session: AsyncSession,
    document_id: uuid.UUID,
    instruction: str,
    expected_lock_version: int,
    platform: str | None = None,
    style_rules: str | None = None,
    word_count: int = 1000,
    extra_context: str | None = None,
) -> AsyncIterator[str]:
    result = await session.execute(
        select(AnswerDocument)
        .options(selectinload(AnswerDocument.source_item))
        .where(AnswerDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ValueError(f"Document {document_id} not found")

    doc_service = DocumentService(session)
    doc_service._check_lock(doc, expected_lock_version)

    title = doc.source_item.title if doc.source_item else "无标题"
    content_mode = "answer"
    if doc and doc.source_item and doc.source_item.raw_metadata:
        content_mode = doc.source_item.raw_metadata.get("content_mode") or "answer"

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
            content=doc.source_item.content if doc.source_item else "",
            instruction=instruction,
            content_mode=content_mode,
        )
        rendered.messages.extend(user_rendered.messages)
    except Exception as e:
        logger.error("Failed to render prompt for full rewrite: %s", e)
        raise

    async for delta in run_writer_stream(
        session,
        "full_rewrite",
        document_id,
        rendered,
        expected_lock_version,
        platform=platform,
        extra_context=extra_context,
        version_extra={"instruction": instruction},
    ):
        yield delta
