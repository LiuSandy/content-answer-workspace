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
from ..nodes.retrieve_knowledge import retrieve_knowledge_node
from ..nodes.knowledge_decision import make_knowledge_decision
from ..nodes.memory_retriever import memory_retriever_node
from ..nodes.platform_collect import has_platform_search_route, platform_collect_node
from ..nodes.task_plan import task_plan_node
from ..nodes.multi_agent_exec import multi_agent_node
from ..nodes.hitl_decision import hitl_decision_node
from ..state import ChatAgentState


from langgraph.prebuilt import ToolNode, tools_condition
from ..tools import ALL_TOOLS


def _route_after_intent(state: ChatAgentState) -> str:
    intent = state.get("intent", "chat")
    if intent == "parse_url":
        return "parse_url"
    if intent == "task_plan":
        return "task_plan"
    if intent == "multi_agent":
        return "multi_agent"
    if has_platform_search_route(state):
        return "platform_collect"
    return "knowledge_decision"


async def knowledge_decision_node(state: ChatAgentState) -> dict:
    """决定是否需要 RAG 检索；决策逻辑唯一入口是 make_knowledge_decision。"""
    mode = state.get("knowledge_mode", "normal")
    needed, reason = make_knowledge_decision(state.get("user_message", ""), mode)
    return {"rag_decision": needed, "decision_reason": reason}


def _route_after_knowledge_decision(state: ChatAgentState) -> str:
    if not state.get("rag_decision", False):
        return "chat"
    return "retrieve_knowledge"


def _route_after_retrieval(state: ChatAgentState) -> str:
    mode = state.get("knowledge_mode", "normal")
    result = state.get("retrieval_result")
    if result and getattr(result, "has_evidence", False):
        return "chat"  # chat_node 会读取 retrieval_result 注入 grounded context
    if mode == "strict":
        return "strict_refusal"
    return "chat"  # fallback: chat_node 依据 retrieval_result.has_evidence 提示"通用知识作答"


async def strict_refusal_node(state: ChatAgentState) -> dict:
    from langchain_core.messages import AIMessage
    msg = AIMessage(content="私有资料库中没有足够的相关证据，在严格知识库模式下无法回答该问题。请切换至普通模式或补充相关资料后重试。")
    return {"messages": [msg]}


def _route_after_chat(state: ChatAgentState) -> str:
    """chat 节点后路由：有工具调用则执行工具；否则直接结束。"""
    result = tools_condition(state)
    if result == END:
        return END
    return "tools"


def _route_after_hitl(state: ChatAgentState) -> str:
    """hitl_decision 后：已请求用户选择则终态；否则回到 chat 继续生成。"""
    if state.get("hitl_pending"):
        return END
    return "chat"


def build_chat_agent_graph(checkpointer: BaseCheckpointSaver):
    """构建新的 Chat Agent 图。"""
    graph: StateGraph = StateGraph(ChatAgentState)

    graph.add_node("preprocess", preprocess_node)
    graph.add_node("memory_retriever", memory_retriever_node)
    graph.add_node("route_intent", route_intent_node)
    
    graph.add_node("knowledge_decision", knowledge_decision_node)
    graph.add_node("retrieve_knowledge", retrieve_knowledge_node)
    graph.add_node("strict_refusal", strict_refusal_node)
    graph.add_node("task_plan", task_plan_node)
    graph.add_node("multi_agent", multi_agent_node)
    graph.add_node("platform_collect", platform_collect_node)
    graph.add_node("hitl_decision", hitl_decision_node)
    
    graph.add_node("chat", chat_node)
    graph.add_node("chat_tools", ToolNode(ALL_TOOLS))
    graph.add_node("parse_url", parse_url_node)
    graph.add_node("normalize_and_persist", normalize_and_persist_node)
    graph.add_node("build_response", build_response_node)

    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "memory_retriever")
    graph.add_edge("memory_retriever", "route_intent")
    graph.add_conditional_edges(
        "route_intent",
        _route_after_intent,
        {
            "knowledge_decision": "knowledge_decision",
            "parse_url": "parse_url",
            "task_plan": "task_plan",
            "multi_agent": "multi_agent",
            "platform_collect": "platform_collect",
        },
    )
    
    graph.add_conditional_edges(
        "knowledge_decision",
        _route_after_knowledge_decision,
        {"chat": "chat", "retrieve_knowledge": "retrieve_knowledge"},
    )
    
    graph.add_conditional_edges(
        "retrieve_knowledge",
        _route_after_retrieval,
        {"chat": "chat", "strict_refusal": "strict_refusal"}
    )
    
    graph.add_edge("strict_refusal", END)
    
    # 复合任务 / 多 Agent 协作产出即终态
    graph.add_edge("task_plan", END)
    graph.add_edge("multi_agent", END)
    graph.add_edge("platform_collect", END)
    
    # 将 chat 节点扩展为支持工具的 ReAct 环路
    # 工具执行后先经 hitl_decision：若工具结果带冲突，则请求用户选择（终态）；
    # 无冲突则回到 chat 继续生成回复。
    graph.add_conditional_edges(
        "chat",
        _route_after_chat,
        {"tools": "chat_tools", END: END}
    )
    graph.add_edge("chat_tools", "hitl_decision")
    graph.add_conditional_edges(
        "hitl_decision",
        _route_after_hitl,
        {"chat": "chat", END: END}
    )
    
    graph.add_edge("parse_url", "normalize_and_persist")
    graph.add_edge("normalize_and_persist", "build_response")
    graph.add_edge("build_response", END)

    return graph.compile(checkpointer=checkpointer)



# 向后兼容：保留旧名称供 server.py 使用
def build_conversation_graph(checkpointer: BaseCheckpointSaver):
    return build_chat_agent_graph(checkpointer)
