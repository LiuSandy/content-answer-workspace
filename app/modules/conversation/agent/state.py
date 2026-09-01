"""Conversation graph state owned exclusively by the Conversation module."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

from app.shared.dto import AgentError, ChatResponsePayload, CollectionRequest, ToolResult


class ChatAgentState(TypedDict):
    chat_id: str
    user_message_id: str
    user_message: str
    guard_blocked: bool | None
    guard_reason: str | None
    messages: Annotated[list, add_messages]
    intent: Literal["chat", "parse_url", "collect", "task_plan", "multi_agent"] | None
    intent_confidence: float | None
    intent_reason: str | None
    intent_platform: str | None
    intent_query: str | None
    intent_limit: int | None
    intent_sort: Literal["relevance", "hot", "latest"] | None
    platform_collect_result: dict | None
    extracted_urls: list[str]
    collection_request: CollectionRequest | None
    tool_result: ToolResult | None
    response_payload: ChatResponsePayload | None
    error: AgentError | None
    task_plan_result: dict | None
    multi_agent_result: dict | None
    workspace_id: str
    owner_id: str
    knowledge_mode: str
    rag_decision: bool | None
    decision_reason: str | None
    retrieval_result: Any | None
    trace_id: str | None
    fallback_reason: str | None
    applied_memories: list[dict] | None
    hitl_pending: bool | None
    hitl_choice: dict | None
    hitl_selection: str | None
    branch_summary: str | None
    composer_meta: dict | None


class ConversationState(TypedDict):
    messages: Annotated[list, add_messages]


AgentState = ChatAgentState

__all__ = ["AgentState", "ChatAgentState", "ConversationState"]
