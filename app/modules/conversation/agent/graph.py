"""新 Chat Agent 图；包含预处理、意图路由、工具节点和响应构造。"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.plugins.tools.builtin import ALL_TOOLS
from app.modules.conversation.agent.state import ChatAgentState

from .nodes.chat import chat_node
from .nodes.guard import guard_node, route_after_guard
from .nodes.hitl_decision import hitl_decision_node
from .nodes.knowledge_decision import knowledge_decision_node
from .nodes.memory_retriever import (
    answer_preference_memory_retriever_node,
    chat_memory_retriever_node,
)
from .nodes.platform_collect import has_platform_search_route, platform_collect_node
from .nodes.retrieve_knowledge import retrieve_knowledge_node
from .nodes.route_intent import route_intent_node
from .nodes.strict_refusal import strict_refusal_node
from .nodes.tool_nodes import (
    build_response_node,
    normalize_and_persist_node,
    parse_url_node,
)
from .nodes.writer_dispatch import build_writer_dispatch_node


def _route_after_intent(state: ChatAgentState) -> str:
    intent = state.get("intent", "chat")
    if intent == "parse_url":
        return "parse_url"
    if intent == "collect":
        return "platform_collect"
    if intent == "task_plan":
        return "writer"
    if intent == "multi_agent":
        return "writer"
    if has_platform_search_route(state):
        return "platform_collect"
    return "knowledge_decision"


def _route_after_knowledge_decision(state: ChatAgentState) -> str:
    if not state.get("rag_decision", False):
        return "chat_memory"
    return "retrieve_knowledge"


def _route_after_retrieval(state: ChatAgentState) -> str:
    mode = state.get("knowledge_mode", "normal")
    result = state.get("retrieval_result")
    if result and getattr(result, "has_evidence", False):
        return "answer_preference_memory"
    if mode == "strict":
        return "strict_refusal"
    return "chat_memory"


def _route_after_chat(state: ChatAgentState) -> str:
    """chat 节点后路由：有工具调用则执行工具；否则直接结束。"""
    result = tools_condition(state)
    if result == END:
        return END
    return "tools"


def build_chat_agent_graph(checkpointer: BaseCheckpointSaver, writer_graph=None):
    """构建新的 Chat Agent 图。"""
    graph: StateGraph = StateGraph(ChatAgentState)

    graph.add_node("guard", guard_node)
    graph.add_node("route_intent", route_intent_node)

    graph.add_node("knowledge_decision", knowledge_decision_node)
    graph.add_node("retrieve_knowledge", retrieve_knowledge_node)
    graph.add_node("chat_memory", chat_memory_retriever_node)
    graph.add_node(
        "answer_preference_memory",
        answer_preference_memory_retriever_node,
    )
    graph.add_node("strict_refusal", strict_refusal_node)
    graph.add_node("writer", build_writer_dispatch_node(writer_graph))
    graph.add_node("platform_collect", platform_collect_node)
    graph.add_node("hitl_decision", hitl_decision_node)

    graph.add_node("chat", chat_node)
    graph.add_node("chat_tools", ToolNode(ALL_TOOLS))
    graph.add_node("parse_url", parse_url_node)
    graph.add_node("normalize_and_persist", normalize_and_persist_node)
    graph.add_node("build_response", build_response_node)

    graph.add_edge(START, "guard")
    graph.add_conditional_edges(
        "guard",
        route_after_guard,
        {"continue": "route_intent", "blocked": END},
    )
    graph.add_conditional_edges(
        "route_intent",
        _route_after_intent,
        {
            "knowledge_decision": "knowledge_decision",
            "parse_url": "parse_url",
            "writer": "writer",
            "platform_collect": "platform_collect",
        },
    )

    graph.add_conditional_edges(
        "knowledge_decision",
        _route_after_knowledge_decision,
        {
            "chat_memory": "chat_memory",
            "retrieve_knowledge": "retrieve_knowledge",
        },
    )

    graph.add_conditional_edges(
        "retrieve_knowledge",
        _route_after_retrieval,
        {
            "answer_preference_memory": "answer_preference_memory",
            "chat_memory": "chat_memory",
            "strict_refusal": "strict_refusal",
        },
    )

    graph.add_edge("chat_memory", "chat")
    graph.add_edge("answer_preference_memory", "chat")
    graph.add_edge("strict_refusal", END)

    # 复合任务 / 多 Agent 协作产出即终态
    graph.add_edge("writer", END)
    graph.add_edge("platform_collect", END)

    # 将 chat 节点扩展为支持工具的 ReAct 环路
    # 工具执行后先经 hitl_decision：若工具结果带冲突，则请求用户选择（终态）；
    # 无冲突则回到 chat 继续生成回复。
    graph.add_conditional_edges(
        "chat",
        _route_after_chat,
        {"tools": "chat_tools", END: END},
    )
    graph.add_edge("chat_tools", "hitl_decision")
    graph.add_edge("hitl_decision", "chat")

    graph.add_edge("parse_url", "normalize_and_persist")
    graph.add_edge("normalize_and_persist", "build_response")
    graph.add_edge("build_response", END)

    agent = graph.compile(checkpointer=checkpointer)
    print(agent.get_graph().draw_mermaid())

    return agent

__all__ = ["build_chat_agent_graph"]
