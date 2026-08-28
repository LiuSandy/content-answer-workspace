"""按 Chat 分支召回适用范围不同的长期记忆。"""
from __future__ import annotations

import logging

from app.state import ChatAgentState

logger = logging.getLogger(__name__)


async def _retrieve_for_scopes(
    state: ChatAgentState,
    *,
    scopes: set[str],
    top_k: int,
) -> dict:
    from app.services.memory.service import retrieve_memories

    user_message = state.get("user_message", "")
    workspace_id = state.get("workspace_id", "default")

    if not user_message.strip():
        return {"applied_memories": []}

    try:
        snippets = await retrieve_memories(
            query=user_message,
            workspace_id=workspace_id,
            top_k=top_k,
            scopes=scopes,
        )
        return {
            "applied_memories": [
                {
                    "id": s.id,
                    "memory_type": s.memory_type,
                    "memory_scope": s.memory_scope,
                    "content": s.content,
                    "confidence": s.confidence,
                }
                for s in snippets
            ]
        }
    except Exception as e:
        logger.warning("Memory retrieval failed (non-blocking): %s", e)
        return {"applied_memories": []}


async def chat_memory_retriever_node(state: ChatAgentState) -> dict:
    """普通对话召回通用背景、表达方式和受众偏好。"""
    return await _retrieve_for_scopes(
        state,
        scopes={
            "general",
            "conversation",
            "answer_format",
            "writing_style",
            "audience",
        },
        top_k=3,
    )


async def answer_preference_memory_retriever_node(state: ChatAgentState) -> dict:
    """知识库回答只召回展示偏好，不允许长期记忆影响事实边界。"""
    return await _retrieve_for_scopes(
        state,
        scopes={"answer_format", "writing_style", "audience"},
        top_k=2,
    )


__all__ = [
    "answer_preference_memory_retriever_node",
    "chat_memory_retriever_node",
]
