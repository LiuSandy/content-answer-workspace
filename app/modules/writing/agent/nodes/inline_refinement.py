"""局部润色工作流（roadmap R7：薄适配器，委托 WriterService）。"""
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.application.documents import DocumentService
from app.modules.writing.application.writing_service import run_writer_stream
from app.shared.dto import SelectionDTO
from app.shared.errors import ValidationError
from app.platform.prompts.registry import prompt_registry

logger = logging.getLogger(__name__)


async def inline_refinement_workflow(
    session: AsyncSession,
    document_id: uuid.UUID,
    selection: SelectionDTO,
    instruction: str,
    expected_lock_version: int,
) -> AsyncIterator[str]:
    doc_service = DocumentService(session)
    doc = await doc_service._get_doc_or_raise(document_id)
    doc_service._check_lock(doc, expected_lock_version)

    content = doc.current_content or ""
    start_pos = selection.from_pos
    end_pos = selection.to_pos

    if content[start_pos:end_pos] != selection.text:
        idx = content.find(selection.text)
        if idx != -1:
            start_pos = idx
            end_pos = idx + len(selection.text)
        else:
            raise ValidationError("选区文本与当前文档内容不匹配，请刷新页面后重试。")

    context_before = content[:start_pos]
    context_after = content[end_pos:]

    try:
        rendered = prompt_registry.render(
            "refinement.inline_refine",
            selected_text=selection.text,
            context_before=context_before[-1000:],
            context_after=context_after[:1000],
            instruction=instruction,
        )
    except Exception as e:
        logger.error("Failed to render prompt for inline refinement: %s", e)
        raise

    async for delta in run_writer_stream(
        session,
        "refine",
        document_id,
        rendered,
        expected_lock_version,
        content_assembler=lambda parts: context_before + "".join(parts) + context_after,
        version_extra={"instruction": instruction},
    ):
        yield delta
