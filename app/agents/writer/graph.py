from __future__ import annotations

import asyncio
from functools import partial

from langgraph.graph import END, START, StateGraph

from app.services.llm_service import DeepSeekLLMAdapter
from .nodes.apply_instruction import apply_instruction_node
from .nodes.fetch_answer import fetch_answer_node
from .nodes.save_answer import save_answer_node
from app.contracts.agent_ports import SessionServicePort
from app.agents.orchestrator.state import MultiAgentState, SubAgentState
from app.services.planning_service import _get_planner_llm
from app.state import AgentState


async def writing_agent_node(state: MultiAgentState) -> dict:
    """根据 Researcher 产出的研究报告生成初稿。"""
    sub = SubAgentState(name="writing", status="running")
    state.sub_agent_states["writing"] = sub
    sub.started_at = asyncio.get_event_loop().time()

    try:
        llm = _get_planner_llm()
        prompt = (
            "你是一位内容写作专家。请基于研究报告生成结构化的初稿。\n\n"
            f"创作目标：{state.plan.goal}\n\n"
            f"研究报告：\n{state.research_report or '（无研究报告）'}\n\n"
            "请输出完整的 Markdown 正文。"
        )
        state.draft = await llm.analyze("你是写作子 Agent，只产出初稿正文。", prompt)
        sub.result = {"draft_length": len(state.draft or "")}
        sub.status = "done"
    except Exception as error:
        sub.status = "failed"
        sub.error = str(error)
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

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
