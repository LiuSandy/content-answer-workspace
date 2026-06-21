from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from ..nodes.chat import chat_node
from ..state import ConversationState
from ..tools import ALL_TOOLS


def build_conversation_graph(checkpointer: BaseCheckpointSaver):
    """构建 ReAct 对话 Graph；model 节点有工具调用时路由到 tools 节点，否则直接结束。"""
    graph: StateGraph = StateGraph(ConversationState)

    graph.add_node("model", chat_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", tools_condition)
    graph.add_edge("tools", "model")

    return graph.compile(checkpointer=checkpointer)
