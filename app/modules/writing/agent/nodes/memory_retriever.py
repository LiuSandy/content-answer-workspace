"""Writer Graph 专用长期记忆召回节点。"""
from __future__ import annotations

import logging

from app.modules.writing.agent.state import WriterState
from app.modules.writing.agent.progress import emit_progress

logger = logging.getLogger(__name__)

_WRITER_SCOPES = {
    "general",
    "answer_format",
    "writing_style",
    "audience",
    "platform",
    "source_preference",
    "workflow",
}


def _writer_memory_query(state: WriterState) -> str:
    operation = state.get("operation", "compose")
    if operation == "compose":
        return state.get("goal", "")
    return " ".join(
        part
        for part in (
            state.get("title"),
            state.get("instruction"),
            state.get("platform"),
        )
        if part
    )


async def writer_memory_retriever_node(state: WriterState) -> dict:
    emit_progress(state, "retrieve_memory")
    from app.modules.memory.application.manage_memory import retrieve_memories

    query = _writer_memory_query(state).strip()
    if not query:
        emit_progress(state, "retrieve_memory", "completed")
        return {"applied_memories": []}
    try:
        snippets = await retrieve_memories(
            query=query,
            workspace_id=state.get("workspace_id", "default"),
            top_k=5,
            scopes=_WRITER_SCOPES,
        )
        result = {
            "applied_memories": [
                {
                    "id": item.id,
                    "memory_type": item.memory_type,
                    "memory_scope": item.memory_scope,
                    "content": item.content,
                    "confidence": item.confidence,
                }
                for item in snippets
            ]
        }
        emit_progress(state, "retrieve_memory", "completed")
        return result
    except Exception as exc:  # Writer memory remains non-blocking
        logger.warning("Writer memory retrieval failed (non-blocking): %s", exc)
        emit_progress(state, "retrieve_memory", "completed", detail="记忆召回不可用，继续创作")
        return {"applied_memories": []}


__all__ = ["writer_memory_retriever_node"]
