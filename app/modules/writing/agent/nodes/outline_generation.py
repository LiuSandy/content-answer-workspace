"""Article-outline node for the unified full-writing flow."""
from __future__ import annotations

import uuid

from app.modules.writing.application.llm import get_writing_llm
from app.modules.writing.application.outline import OutlineService
from app.modules.documents.adapters.db.models import AnswerDocument
from app.modules.writing.agent.state import WriterState
from app.platform.prompts.registry import prompt_registry
from app.modules.writing.agent.progress import emit_progress


def _outline_source(state: WriterState) -> str:
    parts = [
        f"创作目标：{state.get('goal', '')}",
        f"研究报告：{state.get('research_report') or '（无研究报告）'}",
    ]
    if state.get("creation_mode") == "rewrite" and state.get("content"):
        parts.append(f"当前文章：\n{state['content']}")
    return "\n\n".join(parts)


async def generate_outline_node(state: WriterState) -> dict:
    """Generate a mandatory article outline after research.

    Document runs persist the outline through OutlineService; chat runs keep it
    in WriterState for the subsequent drafting prompt.
    """
    emit_progress(state, "generate_outline")
    try:
        source = _outline_source(state)
        if state.get("session") and state.get("document_id"):
            source_item_id = state.get("source_item_id")
            if source_item_id is None:
                document = await state["session"].get(AnswerDocument, state["document_id"])
                source_item_id = document.source_item_id if document else None
            if source_item_id is None:
                raise ValueError("大纲生成失败：文档缺少来源内容")
            result = await OutlineService(state["session"]).generate(
                document_id=state["document_id"],
                source_item_id=source_item_id,
                workspace_id=state.get("workspace_id", "default"),
                expected_lock_version=state["expected_lock_version"],
                additional_context=source,
            )
            output = {
                "outline": result.outline,
                "outline_operation_id": uuid.UUID(result.operation_id),
                "outline_error": None,
            }
        else:
            rendered = prompt_registry.render(
                "outline.answer_outline",
                source_content=source,
            )
            messages = rendered.to_llm_request().messages
            raw = await get_writing_llm().analyze(
                messages[0].content if messages else "你是文章大纲专家。",
                messages[1].content if len(messages) > 1 else source,
                provider=rendered.provider,
                model=rendered.model,
                temperature=rendered.temperature,
                max_tokens=rendered.max_tokens,
            )
            parsed = OutlineService.parse_outline_json(raw)
            outline = parsed.get("outline") or []
            if not outline:
                raise ValueError("大纲生成失败：模型未返回有效大纲")
            output = {"outline": outline, "outline_error": None}
        emit_progress(state, "generate_outline", "completed")
        return output
    except Exception:
        emit_progress(state, "generate_outline", "failed")
        raise


__all__ = ["generate_outline_node"]
