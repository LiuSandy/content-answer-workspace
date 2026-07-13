"""全文重写工作流；根据指示重写整个回答，流式返回新文本并持久化版本。"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.document_service import DocumentService
from ..infrastructure.llm.registry import llm_provider_registry
from ..persistence.models.documents import AnswerDocument, AIOperation, VERSION_TYPE_FULL_REWRITE
from ..prompts.registry import prompt_registry

logger = logging.getLogger(__name__)


async def full_rewrite_workflow(
    session: AsyncSession,
    document_id: uuid.UUID,
    instruction: str,
    expected_lock_version: int,
) -> AsyncIterator[str]:
    """全文重写工作流；流式返回重写的增量文本，在流结束时写入数据库新版本。"""
    # 1. 查询 Document 和 SourceItem
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
    current_answer = doc.current_content or ""

    # 2. 渲染 Prompt
    try:
        rendered = prompt_registry.render(
            "writing.answer_rewrite",
            title=title,
            current_answer=current_answer,
            instruction=instruction,
        )
    except Exception as e:
        logger.error("Failed to render prompt for full rewrite: %s", e)
        raise

    # 3. 获取 LLM Provider
    provider = llm_provider_registry.get("deepseek")

    # 4. 创建 AIOperation 记录
    ai_op = AIOperation(
        id=uuid.uuid4(),
        document_id=document_id,
        operation_type="full_rewrite",
        status="running",
        prompt_id=rendered.prompt_id,
        prompt_version="1.0.0",
        provider=provider.key,
        model=rendered.model,
        model_parameters={"temperature": rendered.temperature, "max_tokens": rendered.max_tokens},
    )
    session.add(ai_op)
    await session.commit()

    start_time = time.time()
    full_content_parts = []
    input_tokens = 0
    output_tokens = 0

    try:
        llm_req = rendered.to_llm_request()
        async for event in provider.stream(llm_req):
            if event.delta:
                full_content_parts.append(event.delta)
                yield event.delta
            if event.input_tokens is not None:
                input_tokens = event.input_tokens
            if event.output_tokens is not None:
                output_tokens = event.output_tokens

        # 5. 生成完成，保存为新版本
        full_content = "".join(full_content_parts)
        version = await doc_service.create_version(
            document_id=document_id,
            content=full_content,
            version_type=VERSION_TYPE_FULL_REWRITE,
            expected_lock_version=expected_lock_version,
            instruction=instruction,
            prompt_id=rendered.prompt_id,
            prompt_version="1.0.0",
            provider=provider.key,
            model=rendered.model,
        )

        # 6. 更新 AIOperation 状态
        ai_op.status = "completed"
        ai_op.result_version_id = version.id
        ai_op.input_tokens = input_tokens
        ai_op.output_tokens = output_tokens or len(full_content) // 2
        ai_op.latency_ms = int((time.time() - start_time) * 1000)
        await session.commit()

    except Exception as e:
        logger.error("Full rewrite workflow failed: %s", e)
        try:
            ai_op.status = "failed"
            ai_op.error_code = getattr(e, "error_code", "rewrite_failed")
            ai_op.error_message = str(e)
            ai_op.latency_ms = int((time.time() - start_time) * 1000)
            await session.commit()
        except Exception as inner_e:
            logger.error("Failed to update AI operation failure status: %s", inner_e)
        raise e
