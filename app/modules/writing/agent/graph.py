"""The project's single Writer graph.

Planner, Researcher, Drafter, Reviewer, and Memory are ordinary business nodes
over one shared state. No node in this graph compiles another graph.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.modules.writing.agent.nodes.guard import route_after_writer_guard, writer_guard_node
from app.modules.writing.agent.nodes.document_pipeline import (
    inline_refine_document_node,
    route_writer_operation,
)
from app.modules.writing.agent.nodes.memory_retriever import writer_memory_retriever_node
from app.modules.writing.agent.nodes.outline_generation import generate_outline_node
from app.modules.writing.agent.nodes.pipeline import (
    finalize_writer_node,
    research_node,
    review_node,
    write_node,
    writer_memory_node,
)
from app.modules.writing.agent.nodes.planner import assign_node, plan_node, route_after_assignment
from app.modules.writing.agent.state import WriterState


def build_writer_graph():
    builder = StateGraph(WriterState)
    builder.add_node("guard", writer_guard_node)
    builder.add_node("retrieve_memory", writer_memory_retriever_node)
    builder.add_node("inline_refine_document", inline_refine_document_node)
    builder.add_node("generate_outline", generate_outline_node)
    builder.add_node("generate_plan", plan_node)
    builder.add_node("assign_tasks", assign_node)
    builder.add_node("research", research_node)
    builder.add_node("write", write_node)
    builder.add_node("review", review_node)
    builder.add_node("memory", writer_memory_node)
    builder.add_node("finalize", finalize_writer_node)

    builder.add_edge(START, "guard")
    builder.add_conditional_edges(
        "guard",
        route_after_writer_guard,
        {"continue": "retrieve_memory", "blocked": END},
    )
    builder.add_conditional_edges(
        "retrieve_memory",
        route_writer_operation,
        {
            "compose": "generate_plan",
            "inline_refine": "inline_refine_document",
        },
    )
    builder.add_edge("generate_plan", "assign_tasks")
    builder.add_conditional_edges(
        "assign_tasks",
        route_after_assignment,
        {"research": "research", "end": END},
    )
    builder.add_edge("research", "generate_outline")
    builder.add_edge("generate_outline", "write")
    builder.add_edge("write", "review")
    builder.add_edge("review", "memory")
    builder.add_edge("memory", "finalize")
    builder.add_edge("finalize", END)
    builder.add_edge("inline_refine_document", END)
    agent = builder.compile()
    # 输出实际编译后的 Writer Graph，便于核对节点和连线是否与代码一致。
    print(agent.get_graph().draw_mermaid())
    return agent


writer_graph = build_writer_graph()


__all__ = ["build_writer_graph", "writer_graph"]
