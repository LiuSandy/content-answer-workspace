"""回答生成工作流；从 Prompt Registry 获取模板，调用 LLM 流式生成并持久化版本。"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..application.document_service import DocumentService
from ..errors import DocumentConflictError
from ..domain.dto import LLMRequest
from ..infrastructure.llm.registry import llm_provider_registry
from ..persistence.models.documents import AIOperation, VERSION_TYPE_INITIAL_GENERATION
from ..prompts.registry import prompt_registry

from ..persistence.models.content import SourceItem

logger = logging.getLogger("uvicorn")


async def generate_answer_workflow(
    session: AsyncSession,
    source_item_id: uuid.UUID,
    document_id: uuid.UUID,
    platform: str,
    title: str,
    content: str | None,
    expected_lock_version: int,
    style_rules: str | None = None,
    word_count: int = 1000,
    instruction: str | None = None,
) -> AsyncIterator[str]:
    """生成回答工作流；流式返回生成的增量文本，在流结束时写入数据库版本。"""
    # 1. 查找 source_item 详情获取 content_mode
    source_item = await session.get(SourceItem, source_item_id)
    content_mode = "answer"
    if source_item and source_item.raw_metadata:
        content_mode = source_item.raw_metadata.get("content_mode") or "answer"

    # 2. 渲染 Prompt
    try:
        rendered = prompt_registry.render(
            "writing.answer_generate",
        )
        
        # 动态拼接 platform 与 style_rules 到 system 提示词中
        from jinja2 import Template
        for msg in rendered.messages:
            if msg.role == "system":
                # 从 prompts/shared/platform_header.yml 读取人设提示词
                header = ""
                header_tpl = prompt_registry._prompts.get("shared.platform_header")
                if header_tpl:
                    header = Template(header_tpl.content).render(platform=platform) + "\n\n"
                    
                original = msg.content
                
                # 获取默认的风格规范
                shared_prompt = prompt_registry._prompts.get("shared.style_rules")
                base_rules = shared_prompt.content.strip() if shared_prompt else ""
                
                # 如果前端传入了特定的风格，则在默认规范后追加
                if style_rules and style_rules.strip():
                    rules = f"{base_rules}\n{style_rules.strip()}"
                else:
                    rules = base_rules
                
                # 从 prompts/shared/style_rules_footer.yml 读取风格尾部提示词
                footer = ""
                footer_tpl = prompt_registry._prompts.get("shared.style_rules_footer")
                if footer_tpl and rules:
                    footer = "\n\n" + Template(footer_tpl.content).render(rules=rules)
                
                # 从 prompts/shared/word_limit_footer.yml 读取字数限制尾部提示词
                word_limit = ""
                word_limit_tpl = prompt_registry._prompts.get("shared.word_limit_footer")
                if word_limit_tpl:
                    word_limit = "\n\n" + Template(word_limit_tpl.content).render(word_count=word_count)
                
                msg.content = f"{header}{original}{footer}{word_limit}"
                break

        # 动态组装并渲染 user 提示词
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
                full_content_parts.append(event.delta)
                yield event.delta
            if event.input_tokens is not None:
                input_tokens = event.input_tokens
            if event.output_tokens is not None:
                output_tokens = event.output_tokens

        # 4. 生成完成，写入版本快照和更新文档
        full_content = "".join(full_content_parts)
        doc_service = DocumentService(session)
        try:
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
        except DocumentConflictError as conflict_err:
            logger.warning(
                "Lock version conflict during answer generation: expected %s, got %s. Retrying with latest lock_version...",
                conflict_err.expected,
                conflict_err.actual,
            )
            # 在流式生成期间出现锁版本自增（如草稿自动保存），拉取最新文档锁版本并平滑重试保存
            current_doc = await doc_service.get_document(document_id)
            latest_lock = current_doc.lock_version if current_doc else None
            version = await doc_service.create_version(
                document_id=document_id,
                content=full_content,
                version_type=VERSION_TYPE_INITIAL_GENERATION,
                expected_lock_version=latest_lock,
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
        logger.exception("Answer generation workflow failed")
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
