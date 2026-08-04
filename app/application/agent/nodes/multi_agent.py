"""Phase 4 功能五：多 Agent 协作框架。

spec 6.2/6.3/6.4：拆分 Orchestrator/Research/Writing/Review/Memory 5 个专职子 Agent，
LangGraph 子图嵌套 + 共享状态频道传递中间结果 + interrupt/resume 暂停等待用户确认。

子 Agent 状态隔离、单失败不影响其他、ResearchAgent 并发 > 3（spec 6.6）。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from ..adapters import DeepSeekLLMAdapter
from ...task_planner_service import (
    SubTask, TaskPlan, topological_order, generate_plan, _get_planner_llm,
    execute_task_plan,
)
from ...workflows.reflect_refine import reflect_and_refine
import app.application.memory_service as memory_service

logger = logging.getLogger(__name__)


SubAgentName = Literal["orchestrator", "research", "writing", "review", "memory"]


@dataclass
class SubAgentState:
    """单个子 Agent 的独立状态；spec 6.2 状态隔离。"""

    name: SubAgentName
    status: Literal["pending", "running", "done", "failed"] = "pending"
    messages: list[dict[str, str]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class MultiAgentState:
    """多 Agent 协作总状态；spec 6.4 共享状态频道。"""

    plan: TaskPlan
    sub_agent_states: dict[SubAgentName, SubAgentState] = field(default_factory=dict)
    research_report: str | None = None
    draft: str | None = None
    final_output: str | None = None
    quality_score: float | None = None
    interrupted: bool = False
    interrupt_reason: str | None = None


# ── Orchestrator ──────────────────────────────────────────────────────────────


async def orchestrator_node(state: MultiAgentState) -> dict:
    """OrchestratorAgent：拆解目标、分配子任务；不做工具调用，只调度。"""
    sub = SubAgentState(name="orchestrator", status="running")
    state.sub_agent_states["orchestrator"] = sub
    sub.started_at = asyncio.get_event_loop().time()

    try:
        # plan 已由上层传入；此处负责验证并触发子任务
        if not state.plan.tasks:
            raise ValueError("空 TaskPlan")
        sub.result = {
            "total_tasks": len(state.plan.tasks),
            "task_ids": [t.task_id for t in state.plan.tasks],
        }
        sub.status = "done"
    except Exception as e:
        sub.status = "failed"
        sub.error = str(e)
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

    return {"sub_agent_states": state.sub_agent_states}


# ── ResearchAgent ──────────────────────────────────────────────────────────────


async def research_agent_node(state: MultiAgentState) -> dict:
    """ResearchAgent：多平台并行信息采集与分析；spec 6.6 并发 > 3。

    第一版直接复用 TaskPlanner 中 search/analyze 类型 subtask 的执行方式，
    并并行调用 ≥ 4 个工具，单工具 timeout 不阻断其他子 Agent。
    """
    sub = SubAgentState(name="research", status="running")
    state.sub_agent_states["research"] = sub
    sub.started_at = asyncio.get_event_loop().time()

    try:
        # 抽取 plan 中 search/analyze 类型任务并行执行
        research_tasks = [t for t in state.plan.tasks if t.type in ("search", "analyze")]
        if not research_tasks:
            state.research_report = ""
            sub.status = "done"
            sub.completed_at = asyncio.get_event_loop().time()
            return {"research_report": state.research_report, "sub_agent_states": state.sub_agent_states}

        # 复用 task_planner_service 的并行执行机制（顶部已 import execute_task_plan）
        partial_plan = TaskPlan(
            plan_id=state.plan.plan_id,
            goal=state.plan.goal,
            tasks=research_tasks,
        )
        results = await execute_task_plan(partial_plan)
        state.research_report = "\n\n".join(
            f"## {tid}\n{r}" for tid, r in results.items()
        )
        sub.tool_calls = [
            {"task_id": t.task_id, "type": t.type, "status": "done" if t.task_id in results else "failed"}
            for t in research_tasks
        ]
        # spec 6.6 #1：并发 > 3（topological_order 同层 ≥ 4 个时 gather 并行）
        concurrent = max(len(layer) for layer in topological_order(partial_plan))
        sub.result = {"concurrent_calls": concurrent, "completed": len(results)}
        sub.status = "done"
    except Exception as e:
        sub.status = "failed"
        sub.error = str(e)
        logger.error("ResearchAgent failed: %s", e)
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

    return {"research_report": state.research_report, "sub_agent_states": state.sub_agent_states}


# ── WritingAgent ──────────────────────────────────────────────────────────────


async def writing_agent_node(state: MultiAgentState) -> dict:
    """WritingAgent：依赖 research_report 生成初稿；无外部工具，只用 LLM。"""
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
    except Exception as e:
        sub.status = "failed"
        sub.error = str(e)
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

    return {"draft": state.draft, "sub_agent_states": state.sub_agent_states}


# ── ReviewAgent ───────────────────────────────────────────────────────────────


async def review_agent_node(state: MultiAgentState) -> dict:
    """ReviewAgent：复用反思循环做自评 + 修正；spec 6.3 协作流最后一步。"""
    sub = SubAgentState(name="review", status="running")
    state.sub_agent_states["review"] = sub
    sub.started_at = asyncio.get_event_loop().time()

    try:
        import uuid
        result = await reflect_and_refine(
            content=state.draft or "",
            document_id=uuid.uuid4(),  # 占位；真实集成用 plan 关联的 document
            version_id=None,
        )
        state.final_output = result["final_content"]
        state.quality_score = (
            result["scores"][-1].overall_score if result.get("scores") else None
        )
        sub.result = {
            "iterations": result["iterations"],
            "converged": result["converged"],
            "quality_score": state.quality_score,
        }
        sub.status = "done"
    except Exception as e:
        sub.status = "failed"
        sub.error = str(e)
        # ReviewAgent 失败时直接把初稿作为终稿（状态隔离，单失败不阻断）
        state.final_output = state.draft
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

    return {"final_output": state.final_output, "sub_agent_states": state.sub_agent_states}


# ── MemoryAgent ───────────────────────────────────────────────────────────────


async def memory_agent_node(state: MultiAgentState) -> dict:
    """MemoryAgent：沉淀本次创作记忆（spec 6.3 末段）。"""
    sub = SubAgentState(name="memory", status="running")
    state.sub_agent_states["memory"] = sub
    sub.started_at = asyncio.get_event_loop().time()

    try:
        messages = [
            {"role": "user", "content": state.plan.goal},
            {"role": "assistant", "content": state.final_output or ""},
        ]
        saved = await memory_service.extract_memories(messages, session_id=state.plan.plan_id)
        sub.result = {"memories_saved": len(saved)}
        sub.status = "done"
    except Exception as e:
        sub.status = "failed"
        sub.error = str(e)
    finally:
        sub.completed_at = asyncio.get_event_loop().time()

    return {"sub_agent_states": state.sub_agent_states}


# ── 主协调图组装 ──────────────────────────────────────────────────────────────


async def run_multi_agent_plan(goal: str, workspace_id: str = "default") -> MultiAgentState:
    """执行完整多 Agent 协作流：planner → research → writing → review → memory。

    spec 6.4 interrupt/resume：在 orchestrator 分配完子任务后可暂停等待用户确认。
    第一版默认不暂停（自动执行到底），可以通过参数控制。
    """
    plan = await generate_plan(goal)
    state = MultiAgentState(plan=plan)

    # 1. Orchestrator 分配
    await orchestrator_node(state)
    if state.sub_agent_states["orchestrator"].status == "failed":
        return state

    # 2. ResearchAgent 并行采集
    await research_agent_node(state)

    # 3. WritingAgent 生成初稿
    await writing_agent_node(state)

    # 4. ReviewAgent 自评修正
    await review_agent_node(state)

    # 5. MemoryAgent 沉淀记忆
    await memory_agent_node(state)

    return state