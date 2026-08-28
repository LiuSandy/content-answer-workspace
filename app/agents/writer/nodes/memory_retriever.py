"""Writer Graph 专用长期记忆召回节点。"""
from __future__ import annotations

import logging

from app.agents.writer.state import WriterState

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
    from app.services.memory.service import retrieve_memories

    query = _writer_memory_query(state).strip()
    if not query:
        return {"applied_memories": []}
    try:
        snippets = await retrieve_memories(
            query=query,
            workspace_id=state.get("workspace_id", "default"),
            top_k=5,
            scopes=_WRITER_SCOPES,
        )
        return {
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
    except Exception as exc:  # Writer memory remains non-blocking
        logger.warning("Writer memory retrieval failed (non-blocking): %s", exc)
        return {"applied_memories": []}


__all__ = ["writer_memory_retriever_node"]
