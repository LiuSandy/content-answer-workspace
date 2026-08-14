"""多 Agent 协作的 Orchestrator LangGraph 父图。"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.orchestrator.nodes import (
    assign_tasks_node,
    finalize_node,
    generate_plan_node,
    route_after_assignment,
    run_memory_node,
)
from app.agents.orchestrator.state import MultiAgentGraphState, MultiAgentState
from app.agents.researcher.graph import researcher_graph
from app.agents.reviewer.graph import reviewer_graph
from app.agents.writer.graph import writer_graph


def build_orchestrator_graph():
    builder = StateGraph(MultiAgentGraphState)
    builder.add_node("generate_plan", generate_plan_node)
    builder.add_node("assign_tasks", assign_tasks_node)
    builder.add_node("researcher", researcher_graph)
    builder.add_node("writer", writer_graph)
    builder.add_node("reviewer", reviewer_graph)
    builder.add_node("memory", run_memory_node)
    builder.add_node("finalize", finalize_node)
    builder.add_edge(START, "generate_plan")
    builder.add_edge("generate_plan", "assign_tasks")
    builder.add_conditional_edges(
        "assign_tasks",
        route_after_assignment,
        {"researcher": "researcher", "end": END},
    )
    builder.add_edge("researcher", "writer")
    builder.add_edge("writer", "reviewer")
    builder.add_edge("reviewer", "memory")
    builder.add_edge("memory", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile()


orchestrator_graph = build_orchestrator_graph()


async def orchestrator_node(state: MultiAgentState) -> dict:
    """兼容旧的单步 Orchestrator 调用方式。"""
    result = assign_tasks_node(
        {"plan": state.plan, "sub_agent_states": state.sub_agent_states}
    )
    state.sub_agent_states = result["sub_agent_states"]
    return result


async def run_multi_agent_plan(
    goal: str,
    workspace_id: str = "default",
) -> MultiAgentState:
    """执行编译后的多 Agent 父图，并返回兼容状态对象。"""
    result = await orchestrator_graph.ainvoke(
        {
            "goal": goal,
            "workspace_id": workspace_id,
            "sub_agent_states": {},
            "interrupted": False,
        }
    )
    return MultiAgentState(
        plan=result["plan"],
        sub_agent_states=result.get("sub_agent_states") or {},
        research_report=result.get("research_report"),
        draft=result.get("draft"),
        final_output=result.get("final_output"),
        quality_score=result.get("quality_score"),
        interrupted=result.get("interrupted", False),
        interrupt_reason=result.get("interrupt_reason"),
    )


__all__ = [
    "build_orchestrator_graph",
    "orchestrator_graph",
    "orchestrator_node",
    "run_multi_agent_plan",
]
