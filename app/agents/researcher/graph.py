"""Researcher Agent 的 LangGraph 子图。"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.orchestrator.state import MultiAgentState
from app.agents.researcher.nodes import (
    build_report_node,
    execute_tasks_node,
    prepare_tasks_node,
    route_after_prepare,
)
from app.agents.researcher.state import ResearcherState


def build_researcher_graph():
    builder = StateGraph(ResearcherState)
    builder.add_node("prepare_tasks", prepare_tasks_node)
    builder.add_node("execute_tasks", execute_tasks_node)
    builder.add_node("build_report", build_report_node)
    builder.add_edge(START, "prepare_tasks")
    builder.add_conditional_edges(
        "prepare_tasks",
        route_after_prepare,
        {
            "execute_tasks": "execute_tasks",
            "build_report": "build_report",
        },
    )
    builder.add_edge("execute_tasks", "build_report")
    builder.add_edge("build_report", END)
    return builder.compile()


researcher_graph = build_researcher_graph()


async def research_agent_node(state: MultiAgentState) -> dict:
    """兼容旧调用方式，内部执行已编译的 Researcher 子图。"""
    result = await researcher_graph.ainvoke(
        {
            "plan": state.plan,
            "sub_agent_states": state.sub_agent_states,
            "research_report": state.research_report,
        }
    )
    state.research_report = result.get("research_report")
    state.sub_agent_states = result["sub_agent_states"]
    return {
        "research_report": state.research_report,
        "sub_agent_states": state.sub_agent_states,
    }


__all__ = ["build_researcher_graph", "research_agent_node", "researcher_graph"]
