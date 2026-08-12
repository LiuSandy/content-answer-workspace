"""WriterService：统一写作入口（roadmap R7）。

generate / refine / rewrite 三种操作共享相同的 AIOperation 生命周期、
LLM 流式输出、版本持久化与锁冲突重试逻辑。
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.dto import LLMRequest
from ..errors import DocumentConflictError
from ..infrastructure.llm.registry import llm_provider_registry
from ..persistence.models.documents import AIOperation, AnswerVersion
from ..prompts.registry import prompt_registry, RenderedPrompt

logger = logging.getLogger("uvicorn")

_VT_INIT = "initial_generation"
_VT_INLINE = "inline_refinement"
_VT_REWRITE = "full_rewrite"


@dataclass
class WriterRunCapture:
    """首次生成流的临时结果，供评审完成后一次性创建正式版本。"""

    operation_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    content: str = ""
    prompt_id: str | None = None
    prompt_version: str = "1.0.0"
    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    outline_operation_id: uuid.UUID | None = None


def _version_type_for(operation: str) -> str:
    mapping = {
        "generate": _VT_INIT,
        "refine": _VT_INLINE,
        "full_rewrite": _VT_REWRITE,
    }
    return mapping.get(operation, _VT_INIT)


async def run_writer_stream(
    session: AsyncSession,
    operation: str,
    document_id: uuid.UUID,
    rendered: RenderedPrompt,
    expected_lock_version: int,
    *,
    platform: str | None = None,
    extra_context: str | None = None,
    content_assembler: callable | None = None,
    version_extra: dict | None = None,
    defer_version: bool = False,
    capture: WriterRunCapture | None = None,
    outline_operation_id: uuid.UUID | None = None,
) -> AsyncIterator[str]:
    """统一的 LLM 执行引擎。

    content_assembler(list[str]) -> str：将流式累积的片段组装为最终全文。
    默认 "".join ；refinement 传入定制函数以合成 context_before+replacement+context_after。

    version_extra：传给 create_version 的额外关键字参数（instruction/prompt_id 等）。
    """
    from ..application.document_service import DocumentService

    if defer_version and capture is None:
        raise ValueError("capture is required when defer_version=True")

    provider = llm_provider_registry.get("deepseek")

    system_text = next(
        (m.content for m in rendered.to_llm_request().messages if m.role == "system"),
        "",
    )
    if extra_context:
        # 将 WritingBackground 注入 system prompt 末尾
        augmented = RenderedPrompt(
            prompt_id=rendered.prompt_id,
            messages=[
                *rendered.messages[:-1],
                type(rendered.messages[0])(
                    role="system",
                    content=system_text + extra_context,
                ),
            ]
            if rendered.messages
            else [],
            model=rendered.model,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
        )
        rendered = augmented

    # 创建 AIOperation
    ai_op = AIOperation(
        id=uuid.uuid4(),
        document_id=document_id,
        operation_type=operation,
        status="running",
        prompt_id=rendered.prompt_id,
        prompt_version="1.0.0",
        provider=provider.key,
        model=rendered.model,
        model_parameters={
            "temperature": rendered.temperature,
            "max_tokens": rendered.max_tokens,
        },
        input_metadata={
            "outlineOperationId": (
                str(outline_operation_id) if outline_operation_id else None
            )
        },
    )
    session.add(ai_op)
    await session.commit()

    start_time = time.time()
    full_parts: list[str] = []
    input_tokens = 0
    output_tokens = 0

    try:
        llm_req = rendered.to_llm_request()
        async for event in provider.stream(llm_req):
            if event.delta:
                full_parts.append(event.delta)
                yield event.delta
            if event.input_tokens is not None:
                input_tokens = event.input_tokens
            if event.output_tokens is not None:
                output_tokens = event.output_tokens

        full_text = (content_assembler or (lambda parts: "".join(parts)))(full_parts)
        latency_ms = int((time.time() - start_time) * 1000)
        if defer_version:
            assert capture is not None
            capture.operation_id = ai_op.id
            capture.document_id = document_id
            capture.content = full_text
            capture.prompt_id = rendered.prompt_id
            capture.prompt_version = "1.0.0"
            capture.provider = provider.key
            capture.model = rendered.model
            capture.input_tokens = input_tokens
            capture.output_tokens = output_tokens or len(full_text) // 2
            capture.latency_ms = latency_ms
            capture.outline_operation_id = outline_operation_id
            return

        doc_service = DocumentService(session)
        version_kwargs: dict = {
            "prompt_id": rendered.prompt_id,
            "prompt_version": "1.0.0",
            "provider": provider.key,
            "model": rendered.model,
        }
        if version_extra:
            version_kwargs.update(version_extra)
        try:
            version = await doc_service.create_version(
                document_id=document_id,
                content=full_text,
                version_type=_version_type_for(operation),
                expected_lock_version=expected_lock_version,
                **version_kwargs,
            )
        except DocumentConflictError as conflict_err:
            logger.warning(
                "Lock version conflict during %s: expected %s, got %s. Retrying with latest.",
                operation,
                conflict_err.expected,
                conflict_err.actual,
            )
            current_doc = await doc_service.get_document(document_id)
            latest_lock = current_doc.lock_version if current_doc else None
            version = await doc_service.create_version(
                document_id=document_id,
                content=full_text,
                version_type=_version_type_for(operation),
                expected_lock_version=latest_lock,
                **version_kwargs,
            )

        ai_op.status = "completed"
        ai_op.result_version_id = version.id
        ai_op.input_tokens = input_tokens
        ai_op.output_tokens = output_tokens or len(full_text) // 2
        ai_op.latency_ms = latency_ms
        await session.commit()

    except Exception as e:
        logger.exception("Writer %s failed", operation)
        try:
            ai_op.status = "failed"
            ai_op.error_code = getattr(e, "error_code", f"{operation}_failed")
            ai_op.error_message = str(e)
            ai_op.latency_ms = int((time.time() - start_time) * 1000)
            await session.commit()
        except Exception as inner_e:
            logger.error("Failed to update AI operation failure status: %s", inner_e)
        raise


async def finalize_deferred_writer_run(
    session: AsyncSession,
    capture: WriterRunCapture,
    final_content: str,
    expected_lock_version: int,
    output_metadata: dict[str, Any],
) -> AnswerVersion:
    """将已评审的首次生成内容落为唯一正式版本，并完成 AI 操作。"""
    from ..application.document_service import DocumentService

    if capture.operation_id is None or capture.document_id is None:
        raise ValueError("capture does not contain a completed deferred writer run")

    operation = await session.get(AIOperation, capture.operation_id)
    if operation is None:
        raise ValueError(f"AI operation {capture.operation_id} not found")

    if operation.status == "completed" and operation.result_version_id is not None:
        existing = await session.get(AnswerVersion, operation.result_version_id)
        if existing is None:
            raise ValueError(
                f"Result version {operation.result_version_id} not found"
            )
        return existing

    doc_service = DocumentService(session)
    version_kwargs = {
        "document_id": capture.document_id,
        "content": final_content,
        "version_type": _VT_INIT,
        "prompt_id": capture.prompt_id,
        "prompt_version": capture.prompt_version,
        "provider": capture.provider,
        "model": capture.model,
        "outline_operation_id": capture.outline_operation_id,
    }
    try:
        version = await doc_service.create_version(
            expected_lock_version=expected_lock_version,
            **version_kwargs,
        )
    except DocumentConflictError as conflict_err:
        logger.warning(
            "Lock version conflict during deferred generate finalization: "
            "expected %s, got %s. Retrying with latest.",
            conflict_err.expected,
            conflict_err.actual,
        )
        current_doc = await doc_service.get_document(capture.document_id)
        latest_lock = current_doc.lock_version if current_doc else None
        version = await doc_service.create_version(
            expected_lock_version=latest_lock,
            **version_kwargs,
        )

    operation.status = "completed"
    operation.result_version_id = version.id
    operation.output_metadata = output_metadata
    operation.input_tokens = capture.input_tokens
    operation.output_tokens = capture.output_tokens
    operation.latency_ms = capture.latency_ms
    await session.commit()
    return version
