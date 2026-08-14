"""Reviewer Agent 的 LangGraph 子图。"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.orchestrator.state import MultiAgentState
from app.agents.reviewer.nodes import (
    finalize_review_node,
    prepare_review_node,
    preserve_draft_node,
    route_after_review,
    run_review_node,
)
from app.agents.reviewer.state import ReviewerState


def build_reviewer_graph():
    builder = StateGraph(ReviewerState)
    builder.add_node("prepare_review", prepare_review_node)
    builder.add_node("run_review", run_review_node)
    builder.add_node("finalize_review", finalize_review_node)
    builder.add_node("preserve_draft", preserve_draft_node)
    builder.add_edge(START, "prepare_review")
    builder.add_edge("prepare_review", "run_review")
    builder.add_conditional_edges(
        "run_review",
        route_after_review,
        {
            "finalize_review": "finalize_review",
            "preserve_draft": "preserve_draft",
        },
    )
    builder.add_edge("finalize_review", END)
    builder.add_edge("preserve_draft", END)
    return builder.compile()


reviewer_graph = build_reviewer_graph()


async def review_agent_node(state: MultiAgentState) -> dict:
    """兼容旧调用方式，内部执行已编译的 Reviewer 子图。"""
    result = await reviewer_graph.ainvoke(
        {
            "plan": state.plan,
            "draft": state.draft,
            "final_output": state.final_output,
            "quality_score": state.quality_score,
            "sub_agent_states": state.sub_agent_states,
        }
    )
    state.final_output = result.get("final_output")
    state.quality_score = result.get("quality_score")
    state.sub_agent_states = result["sub_agent_states"]
    return {
        "final_output": state.final_output,
        "sub_agent_states": state.sub_agent_states,
    }


__all__ = ["build_reviewer_graph", "review_agent_node", "reviewer_graph"]
