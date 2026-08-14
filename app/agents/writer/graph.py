from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.services.llm_service import DeepSeekLLMAdapter
from .nodes import finalize_draft_node, generate_draft_node, prepare_prompt_node
from .nodes.apply_instruction import apply_instruction_node
from .nodes.fetch_answer import fetch_answer_node
from .nodes.save_answer import save_answer_node
from app.contracts.agent_ports import SessionServicePort
from app.agents.orchestrator.state import MultiAgentState
from app.agents.writer.state import WriterState
from app.state import AgentState


def build_writer_graph():
    builder = StateGraph(WriterState)
    builder.add_node("prepare_prompt", prepare_prompt_node)
    builder.add_node("generate_draft", generate_draft_node)
    builder.add_node("finalize_draft", finalize_draft_node)
    builder.add_edge(START, "prepare_prompt")
    builder.add_edge("prepare_prompt", "generate_draft")
    builder.add_edge("generate_draft", "finalize_draft")
    builder.add_edge("finalize_draft", END)
    return builder.compile()


writer_graph = build_writer_graph()


async def writing_agent_node(state: MultiAgentState) -> dict:
    """兼容旧调用方式，内部执行已编译的 Writer 子图。"""
    result = await writer_graph.ainvoke(
        {
            "plan": state.plan,
            "research_report": state.research_report,
            "draft": state.draft,
            "sub_agent_states": state.sub_agent_states,
        }
    )
    state.draft = result.get("draft")
    state.sub_agent_states = result["sub_agent_states"]
    return {"draft": state.draft, "sub_agent_states": state.sub_agent_states}


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
