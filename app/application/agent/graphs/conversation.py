"""新 Chat Agent 图；包含预处理、意图路由、工具节点和响应构造。"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ..nodes.chat_node import chat_node
from ..nodes.preprocess import preprocess_node
from ..nodes.route_intent import route_intent_node
from ..nodes.tool_nodes import (
    build_response_node,
    normalize_and_persist_node,
    parse_url_node,
)
from ..state import ChatAgentState


from langgraph.prebuilt import ToolNode, tools_condition
from ..tools import ALL_TOOLS


def _route_after_intent(state: ChatAgentState) -> str:
    intent = state.get("intent", "chat")
    if intent == "parse_url":
        return "parse_url"
    return "chat"


def build_chat_agent_graph(checkpointer: BaseCheckpointSaver):
    """构建新的 Chat Agent 图。"""
    graph: StateGraph = StateGraph(ChatAgentState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("route_intent", route_intent_node)
    graph.add_node("chat", chat_node)
    graph.add_node("chat_tools", ToolNode(ALL_TOOLS))
    graph.add_node("parse_url", parse_url_node)
    graph.add_node("normalize_and_persist", normalize_and_persist_node)
    graph.add_node("build_response", build_response_node)

    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "route_intent")
    graph.add_conditional_edges(
        "route_intent",
        _route_after_intent,
        {"chat": "chat", "parse_url": "parse_url"},
    )
    
    # 将 chat 节点扩展为支持工具的 ReAct 环路
    graph.add_conditional_edges(
        "chat",
        tools_condition,
        {"tools": "chat_tools", END: END}
    )
    graph.add_edge("chat_tools", "chat")
    
    graph.add_edge("parse_url", "normalize_and_persist")
    graph.add_edge("normalize_and_persist", "build_response")
    graph.add_edge("build_response", END)

    return graph.compile(checkpointer=checkpointer)



# 向后兼容：保留旧名称供 server.py 使用
def build_conversation_graph(checkpointer: BaseCheckpointSaver):
    return build_chat_agent_graph(checkpointer)
