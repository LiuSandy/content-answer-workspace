"""新 Chat Agent State 定义；设计原则见架构文档第 5.2 节。

State 只保存本次图运行需要的数据，不保存编辑器内容、历史版本和凭证。
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict
from langgraph.graph.message import add_messages
from app.contracts.dto import AgentError, ChatResponsePayload, CollectionRequest, ToolResult


class ChatAgentState(TypedDict):
    # ── 输入（请求带入）
    chat_id: str
    user_message_id: str
    user_message: str

    # ── Guard（所有业务节点之前执行）
    guard_blocked: bool | None
    guard_reason: str | None

    # ── 决策数据（节点间传递）
    messages: Annotated[list, add_messages]
    intent: Literal["chat", "parse_url", "collect", "task_plan", "multi_agent"] | None
    # 意图识别明细（规则层/LLM 层产出）
    intent_confidence: float | None
    intent_reason: str | None
    intent_platform: str | None
    intent_query: str | None
    intent_limit: int | None
    intent_sort: Literal["relevance", "hot", "latest"] | None
    # 确定性平台采集结果独立保存，不伪装成 LLM ToolMessage。
    platform_collect_result: dict | None
    extracted_urls: list[str]
    collection_request: CollectionRequest | None
    tool_result: ToolResult | None
    response_payload: ChatResponsePayload | None
    error: AgentError | None

    # ── 复合任务 / 多 Agent 协作结果（Phase 3/4，由意图识别自动触发）
    task_plan_result: dict | None   # {"planId", "goal", "tasks", "status"}
    multi_agent_result: dict | None  # {"status", "agents", "finalContent"}

    # ── RAG 相关字段
    workspace_id: str
    owner_id: str
    knowledge_mode: str  # "off" | "normal" | "strict"
    rag_decision: bool | None
    decision_reason: str | None
    retrieval_result: Any | None  # RetrievalResult dataclass
    trace_id: str | None
    fallback_reason: str | None

    # ── Phase 4 长期记忆注入片段（spec 3.3）
    applied_memories: list[dict] | None

    # ── Human-in-the-loop（Phase 2 采集冲突；通用机制）
    # 本轮是否要求用户选择（Agent 检测到约束冲突时置 True）
    hitl_pending: bool | None
    # 给用户的选择请求（choice_request 消息的持久化快照）
    hitl_choice: dict | None  # {"question", "options": [{id, label, description}], "context": {...}}
    # 用户的选择结果（下一轮由前端回传，Agent 据此继续）
    hitl_selection: str | None

    # ── R4 分支上下文（roadmap R4）
    # 分支级滚动摘要；由 chats 路由从 branch_summaries 注入，chat_node 组装进 system prompt
    branch_summary: str | None
    # 本轮 ContextComposer 组装元数据（预算/裁剪/截断明细，诊断与调试用）
    composer_meta: dict | None


class ConversationState(TypedDict):
    """LangGraph checkpoint 用的简化对话状态；仅保存消息序列，不保存业务数据。"""
    messages: Annotated[list, add_messages]


# 兼容遗留的 AgentState 名称
AgentState = ChatAgentState
