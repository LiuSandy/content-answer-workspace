"""Phase 4 功能五：多 Agent 协作框架。

spec 6.2/6.3/6.4：拆分 Orchestrator/Research/Writing/Review/Memory 5 个专职子 Agent，
LangGraph 子图嵌套 + 共享状态频道传递中间结果 + interrupt/resume 暂停等待用户确认。

子 Agent 状态隔离、单失败不影响其他、ResearchAgent 并发 > 3（spec 6.6）。
"""
from __future__ import annotations

import asyncio
from app.agents.memory.graph import memory_agent_node
from app.agents.researcher.graph import research_agent_node
from app.agents.reviewer.graph import review_agent_node
from app.agents.writer.graph import writing_agent_node
from app.agents.orchestrator.state import MultiAgentState, SubAgentState
from app.services.planning_service import generate_plan


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
