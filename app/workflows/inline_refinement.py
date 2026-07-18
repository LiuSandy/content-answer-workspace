"""局部润色工作流；根据指示优化选中文字，流式返回替换文本并持久化修改。"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..application.document_service import DocumentService
from ..domain.dto import SelectionDTO
from ..errors import ValidationError
from ..infrastructure.llm.registry import llm_provider_registry
from ..persistence.models.documents import AIOperation, VERSION_TYPE_INLINE_REFINEMENT
from ..prompts.registry import prompt_registry

logger = logging.getLogger("uvicorn")


async def inline_refinement_workflow(
    session: AsyncSession,
    document_id: uuid.UUID,
    selection: SelectionDTO,
    instruction: str,
    expected_lock_version: int,
) -> AsyncIterator[str]:
    """局部润色工作流；流式返回替换的增量文本，在流结束时组装全文并写入数据库版本。"""
    # 1. 获取文档当前状态，校验选区是否匹配
    doc_service = DocumentService(session)
    doc = await doc_service._get_doc_or_raise(document_id)
    doc_service._check_lock(doc, expected_lock_version)

    content = doc.current_content or ""
    start_pos = selection.from_pos
    end_pos = selection.to_pos

    # 容错：如果位置不匹配，尝试全局搜索一次
    if content[start_pos:end_pos] != selection.text:
        idx = content.find(selection.text)
        if idx != -1:
            start_pos = idx
            end_pos = idx + len(selection.text)
        else:
            raise ValidationError("选区文本与当前文档内容不匹配，请刷新页面后重试。")

    context_before = content[:start_pos]
    context_after = content[end_pos:]

    # 2. 渲染 Prompt
    try:
        rendered = prompt_registry.render(
            "refinement.inline_refine",
            selected_text=selection.text,
            context_before=context_before[-1000:],  # 截取前 1000 字作为上下文
            context_after=context_after[:1000],    # 截取后 1000 字作为上下文
            instruction=instruction,
        )
    except Exception as e:
        logger.error("Failed to render prompt for inline refinement: %s", e)
        raise

    # 3. 获取 LLM Provider
    provider = llm_provider_registry.get("deepseek")

    # 4. 创建 AIOperation 记录
    ai_op = AIOperation(
        id=uuid.uuid4(),
        document_id=document_id,
        operation_type="inline_refine",
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
    replacement_parts = []
    input_tokens = 0
    output_tokens = 0

    try:
        llm_req = rendered.to_llm_request()

        # ── 打印核心提示词 ────────────────────────────────────────────────
        system_prompt = next((m.content for m in llm_req.messages if m.role == "system"), "")
        user_prompt = next((m.content for m in llm_req.messages if m.role == "user"), "")
        logger.info(
            "\n[System Prompt]:\n%s\n\n[User Prompt]:\n%s\n",
            system_prompt,
            user_prompt
        )
        # ─────────────────────────────────────────────────────────────────

        async for event in provider.stream(llm_req):
            if event.delta:
                replacement_parts.append(event.delta)
                yield event.delta
            if event.input_tokens is not None:
                input_tokens = event.input_tokens
            if event.output_tokens is not None:
                output_tokens = event.output_tokens

        # 5. 合成全文并保存新版本
        replacement_text = "".join(replacement_parts)
        new_content = context_before + replacement_text + context_after

        version = await doc_service.create_version(
            document_id=document_id,
            content=new_content,
            version_type=VERSION_TYPE_INLINE_REFINEMENT,
            expected_lock_version=expected_lock_version,
            instruction=instruction,
            prompt_id=rendered.prompt_id,
            prompt_version="1.0.0",
            provider=provider.key,
            model=rendered.model,
        )

        # 6. 更新 AIOperation
        ai_op.status = "completed"
        ai_op.result_version_id = version.id
        ai_op.input_tokens = input_tokens
        ai_op.output_tokens = output_tokens or len(replacement_text) // 2
        ai_op.latency_ms = int((time.time() - start_time) * 1000)
        await session.commit()

    except Exception as e:
        logger.error("Inline refinement workflow failed: %s", e)
        try:
            ai_op.status = "failed"
            ai_op.error_code = getattr(e, "error_code", "refinement_failed")
            ai_op.error_message = str(e)
            ai_op.latency_ms = int((time.time() - start_time) * 1000)
            await session.commit()
        except Exception as inner_e:
            logger.error("Failed to update AI operation failure status: %s", inner_e)
        raise e
