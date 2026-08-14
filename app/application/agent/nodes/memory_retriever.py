"""Phase 4 长期记忆注入节点；spec 3.3。

Agent 运行开始时从 user_memories 检索相关记忆片段，注入 system prompt 上下文，
让 chat_node 能在回答中体现用户偏好。
"""
from __future__ import annotations

import logging

from ..state import ChatAgentState

logger = logging.getLogger(__name__)


async def memory_retriever_node(state: ChatAgentState) -> dict:
    """在 knowledge_decision 之前/retrieve_knowledge 之后注入记忆。

    检索与 user_message 相关的记忆片段，写入 state.applied_memories 供 chat_node 拼接到
    system prompt。检索超时或失败时不阻断主链路（spec 3.6：≤ 200ms）。
    """
    from app.application.memory_service import retrieve_memories

    user_message = state.get("user_message", "")
    workspace_id = state.get("workspace_id", "default")

    if not user_message.strip():
        return {"applied_memories": []}

    try:
        snippets = await retrieve_memories(
            query=user_message,
            workspace_id=workspace_id,
            top_k=5,
        )
        return {
            "applied_memories": [
                {
                    "id": s.id,
                    "memory_type": s.memory_type,
                    "content": s.content,
                    "confidence": s.confidence,
                }
                for s in snippets
            ]
        }
    except Exception as e:
        logger.warning("Memory retrieval failed (non-blocking): %s", e)
        return {"applied_memories": []}