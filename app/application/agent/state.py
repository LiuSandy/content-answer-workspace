from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ── 输入（请求带入）
    session_id: str
    question_id: str | None
    user_message: str

    # ── 工作数据（节点间传递，请求结束后丢弃）
    current_answer: str | None
    hotlist_items: list[dict] | None

    # ── 输出（最终返回给 API 层）
    reply: str
    answer_updated: bool
    updated_answer: str | None
    operation_summary: str


class ConversationState(TypedDict):
    """对话页面使用的状态；messages 由 add_messages reducer 自动累积历史，不需要手动拼接。"""

    messages: Annotated[list, add_messages]
