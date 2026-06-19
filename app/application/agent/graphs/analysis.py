from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from ..adapters import DeepSeekLLMAdapter, HotlistServiceAdapter
from ..nodes.analyze_hotlist import analyze_hotlist_node
from ..nodes.fetch_hotlist import fetch_hotlist_node
from ..state import AgentState

_analysis_graph = None


def get_analysis_graph():
    """返回进程级单例 AnalysisGraph；无请求级状态，编译开销只发生一次。"""
    global _analysis_graph
    if _analysis_graph is None:
        hotlist_svc = HotlistServiceAdapter()
        llm = DeepSeekLLMAdapter()

        graph: StateGraph = StateGraph(AgentState)
        graph.add_node("fetch_hotlist", partial(fetch_hotlist_node, hotlist_svc=hotlist_svc))
        graph.add_node("analyze", partial(analyze_hotlist_node, llm=llm))

        graph.add_edge(START, "fetch_hotlist")
        graph.add_edge("fetch_hotlist", "analyze")
        graph.add_edge("analyze", END)

        _analysis_graph = graph.compile()
    return _analysis_graph
