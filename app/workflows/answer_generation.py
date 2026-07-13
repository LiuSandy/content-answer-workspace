"""回答生成工作流；从 Prompt Registry 获取模板，调用 LLM 流式生成并持久化版本。"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..application.document_service import DocumentService
from ..domain.dto import LLMRequest
from ..infrastructure.llm.registry import llm_provider_registry
from ..persistence.models.documents import AIOperation, VERSION_TYPE_INITIAL_GENERATION
from ..prompts.registry import prompt_registry

logger = logging.getLogger(__name__)


async def generate_answer_workflow(
    session: AsyncSession,
    source_item_id: uuid.UUID,
    document_id: uuid.UUID,
    platform: str,
    title: str,
    content: str | None,
    expected_lock_version: int,
) -> AsyncIterator[str]:
    """生成回答工作流；流式返回生成的增量文本，在流结束时写入数据库版本。"""
    # 1. 渲染 Prompt
    try:
        rendered = prompt_registry.render(
            "writing.answer_generate",
            title=title,
            content=content or "",
            platform=platform,
        )
    except Exception as e:
        logger.error("Failed to render prompt for answer generation: %s", e)
        raise

    # 2. 获取 LLM Provider
    provider = llm_provider_registry.get("deepseek")

    # 3. 创建 AIOperation 记录并保存
    ai_op = AIOperation(
        id=uuid.uuid4(),
        document_id=document_id,
        operation_type="generate",
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

        # 4. 生成完成，写入版本快照和更新文档
        full_content = "".join(full_content_parts)
        doc_service = DocumentService(session)
        version = await doc_service.create_version(
            document_id=document_id,
            content=full_content,
            version_type=VERSION_TYPE_INITIAL_GENERATION,
            expected_lock_version=expected_lock_version,
            prompt_id=rendered.prompt_id,
            prompt_version="1.0.0",
            provider=provider.key,
            model=rendered.model,
        )

        # 5. 更新 AIOperation 状态
        ai_op.status = "completed"
        ai_op.result_version_id = version.id
        ai_op.input_tokens = input_tokens
        ai_op.output_tokens = output_tokens or len(full_content) // 2  # 兜底估算
        ai_op.latency_ms = int((time.time() - start_time) * 1000)
        ai_op.completed_at = session.bind.clock() if hasattr(session.bind, "clock") else None # SQLAlchemy now() is better
        await session.commit()

    except Exception as e:
        logger.error("Answer generation workflow failed: %s", e)
        # 失败时更新 AIOperation
        try:
            ai_op.status = "failed"
            ai_op.error_code = getattr(e, "error_code", "generation_failed")
            ai_op.error_message = str(e)
            ai_op.latency_ms = int((time.time() - start_time) * 1000)
            await session.commit()
        except Exception as inner_e:
            logger.error("Failed to update AI operation failure status: %s", inner_e)
        raise e
