"""WriterService：统一写作入口（roadmap R7）。

generate / refine / rewrite 三种操作共享相同的 AIOperation 生命周期、
LLM 流式输出、版本持久化与锁冲突重试逻辑。
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.dto import LLMRequest
from ..errors import DocumentConflictError
from ..infrastructure.llm.registry import llm_provider_registry
from ..persistence.models.documents import AIOperation
from ..prompts.registry import prompt_registry, RenderedPrompt

logger = logging.getLogger("uvicorn")

_VT_INIT = "initial_generation"
_VT_INLINE = "inline_refinement"
_VT_REWRITE = "full_rewrite"


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
) -> AsyncIterator[str]:
    """统一的 LLM 执行引擎。

    content_assembler(list[str]) -> str：将流式累积的片段组装为最终全文。
    默认 "".join ；refinement 传入定制函数以合成 context_before+replacement+context_after。

    version_extra：传给 create_version 的额外关键字参数（instruction/prompt_id 等）。
    """
    from ..application.document_service import DocumentService

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
        ai_op.latency_ms = int((time.time() - start_time) * 1000)
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
