from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from ..nodes.chat import chat_node
from ..state import ConversationState


def build_conversation_graph(checkpointer: BaseCheckpointSaver):
    """构建对话页面用的单节点 Graph；checkpointer 由调用方注入和管理生命周期，graph 本身不持有连接。"""

    graph: StateGraph = StateGraph(ConversationState)
    graph.add_node("chat", chat_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)
    return graph.compile(checkpointer=checkpointer)
