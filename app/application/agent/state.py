"""新 Chat Agent State 定义；设计原则见架构文档第 5.2 节。

State 只保存本次图运行需要的数据，不保存编辑器内容、历史版本和凭证。
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict
from langgraph.graph.message import add_messages
from ...domain.dto import AgentError, ChatResponsePayload, CollectionRequest, ToolResult


class ChatAgentState(TypedDict):
    # ── 输入（请求带入）
    chat_id: str
    user_message_id: str
    user_message: str

    # ── 决策数据（节点间传递）
    messages: Annotated[list, add_messages]
    intent: Literal["chat", "parse_url", "collect"] | None
    extracted_urls: list[str]
    collection_request: CollectionRequest | None
    tool_result: ToolResult | None
    response_payload: ChatResponsePayload | None
    error: AgentError | None

    # ── RAG 相关字段
    workspace_id: str
    owner_id: str
    knowledge_mode: str  # "off" | "normal" | "strict"
    rag_decision: bool | None
    decision_reason: str | None
    retrieval_result: Any | None  # RetrievalResult dataclass
    trace_id: str | None
    fallback_reason: str | None


class ConversationState(TypedDict):
    """LangGraph checkpoint 用的简化对话状态；仅保存消息序列，不保存业务数据。"""
    messages: Annotated[list, add_messages]


# 兼容遗留的 AgentState 名称
AgentState = ChatAgentState
