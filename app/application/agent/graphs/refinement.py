from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from ..adapters import DeepSeekLLMAdapter
from ..nodes.apply_instruction import apply_instruction_node
from ..nodes.fetch_answer import fetch_answer_node
from ..nodes.save_answer import save_answer_node
from ..ports import SessionServicePort
from ..state import AgentState


def build_refinement_graph(session_svc: SessionServicePort):
    """构建回答精修 Graph；每次请求创建新实例，绑定请求级 session adapter。"""
    llm = DeepSeekLLMAdapter()

    graph: StateGraph = StateGraph(AgentState)
    graph.add_node("fetch_answer", partial(fetch_answer_node, session_svc=session_svc))
    graph.add_node("apply_instruction", partial(apply_instruction_node, llm=llm))
    graph.add_node("save_answer", partial(save_answer_node, session_svc=session_svc))

    graph.add_edge(START, "fetch_answer")
    graph.add_edge("fetch_answer", "apply_instruction")
    graph.add_edge("apply_instruction", "save_answer")
    graph.add_edge("save_answer", END)

    return graph.compile()
