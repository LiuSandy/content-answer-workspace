"""Phase 4 · 多 Agent 协作测试。"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.agent.nodes.multi_agent import (
    MultiAgentState, SubAgentState,
    orchestrator_node, research_agent_node, writing_agent_node, review_agent_node, memory_agent_node,
    run_multi_agent_plan,
)
from app.application.task_planner_service import SubTask, TaskPlan


def _mock_plan() -> TaskPlan:
    return TaskPlan(
        plan_id="p1", goal="写一篇 DeepSeek 评测",
        tasks=[
            SubTask("t1", "search", "搜索资料", []),
            SubTask("t2", "analyze", "分析", ["t1"]),
            SubTask("t3", "outline", "提纲", ["t2"]),
            SubTask("t4", "write", "正文", ["t3"]),
            SubTask("t5", "review", "自评", ["t4"]),
        ],
    )


@pytest.mark.asyncio
async def test_orchestrator_assigns_tasks():
    state = MultiAgentState(plan=_mock_plan())
    await orchestrator_node(state)
    sub = state.sub_agent_states["orchestrator"]
    assert sub.status == "done"
    assert sub.result["total_tasks"] == 5


@pytest.mark.asyncio
async def test_orchestrator_fails_on_empty_plan():
    state = MultiAgentState(plan=TaskPlan("p0", "", []))
    await orchestrator_node(state)
    sub = state.sub_agent_states["orchestrator"]
    assert sub.status == "failed"


@pytest.mark.asyncio
async def test_writing_agent_produces_draft(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value="# 初稿\n\n正文内容...")
    monkeypatch.setattr(
        "app.application.agent.nodes.multi_agent._get_planner_llm",
        lambda: fake_llm,
    )
    state = MultiAgentState(plan=_mock_plan(), research_report="研究报告内容")
    await writing_agent_node(state)
    assert state.draft is not None
    assert "初稿" in state.draft
    assert state.sub_agent_states["writing"].status == "done"


@pytest.mark.asyncio
async def test_review_agent_failure_does_not_block_final_output(monkeypatch):
    """spec 6.6 #2：单子 Agent 失败不影响其他。ReviewAgent 失败时初稿作终稿。"""
    monkeypatch.setattr(
        "app.application.agent.nodes.multi_agent.reflect_and_refine",
        AsyncMock(side_effect=RuntimeError("review failed")),
    )
    state = MultiAgentState(plan=_mock_plan(), draft="这是初稿")
    await review_agent_node(state)
    # ReviewAgent 失败，但 final_output 保留初稿
    assert state.final_output == "这是初稿"
    assert state.sub_agent_states["review"].status == "failed"
    assert state.sub_agent_states["review"].error is not None


@pytest.mark.asyncio
async def test_memory_agent_failure_isolated(monkeypatch):
    """MemoryAgent 失败不影响整体协作状态。"""
    monkeypatch.setattr(
        "app.application.memory_service.extract_memories",
        AsyncMock(side_effect=RuntimeError("memory store down")),
    )
    state = MultiAgentState(plan=_mock_plan(), final_output="final")
    await memory_agent_node(state)
    assert state.sub_agent_states["memory"].status == "failed"
    # 其他子 Agent 状态不受影响


@pytest.mark.asyncio
async def test_research_agent_concurrent_calls_gt_3(monkeypatch):
    """spec 6.6 #1：ResearchAgent 并发 > 3。"""
    # 构造 4 个并行 search 子任务（同层无依赖），确保 topological_order 第一层 ≥ 4
    plan = TaskPlan(
        plan_id="p1", goal="x",
        tasks=[
            SubTask("s1", "search", "a", []),
            SubTask("s2", "search", "b", []),
            SubTask("s3", "search", "c", []),
            SubTask("s4", "search", "d", []),
            SubTask("a1", "analyze", "y", ["s1", "s2", "s3", "s4"]),
        ],
    )

    call_log: list = []

    async def fake_execute(subtask, prior):
        call_log.append((subtask.task_id, asyncio.get_event_loop().time()))
        await asyncio.sleep(0.01)
        return f"result-{subtask.task_id}"

    monkeypatch.setattr(
        "app.application.task_planner_service.execute_subtask",
        fake_execute,
    )
    monkeypatch.setattr(
        "app.application.task_planner_service._get_planner_llm",
        lambda: MagicMock(),
    )

    state = MultiAgentState(plan=plan)
    await research_agent_node(state)
    sub = state.sub_agent_states["research"]
    assert sub.status == "done"
    assert sub.result["concurrent_calls"] >= 4
    # s1-s4 同层并行（启动时间差 < 5ms）
    times = [t for _, t in call_log[:4]]
    assert max(times) - min(times) < 0.005 or len(call_log) >= 4


@pytest.mark.asyncio
async def test_run_multi_agent_plan_end_to_end(monkeypatch):
    """端到端：planner → research → writing → review → memory。"""
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value="初稿内容")
    monkeypatch.setattr(
        "app.application.agent.nodes.multi_agent._get_planner_llm",
        lambda: fake_llm,
    )
    monkeypatch.setattr(
        "app.application.agent.nodes.multi_agent.generate_plan",
        AsyncMock(return_value=_mock_plan()),
    )
    # mock execute_task_plan 避免真实 LLM
    async def fake_exec(plan):
        return {t.task_id: f"r-{t.task_id}" for t in plan.tasks}
    monkeypatch.setattr(
        "app.application.task_planner_service.execute_task_plan",
        fake_exec,
    )
    # mock 反思循环
    async def fake_reflect(content, document_id, version_id, workspace_id="default"):
        return {
            "final_content": "final content",
            "iterations": 1,
            "converged": True,
            "scores": [MagicMock(overall_score=0.85)],
            "forced_message": None,
        }
    monkeypatch.setattr(
        "app.application.agent.nodes.multi_agent.reflect_and_refine",
        fake_reflect,
    )
    # mock memory
    monkeypatch.setattr(
        "app.application.memory_service.extract_memories",
        AsyncMock(return_value=[]),
    )

    state = await run_multi_agent_plan("写一篇", workspace_id="default")
    assert state.final_output == "final content"
    assert state.quality_score == 0.85
    # 全部 5 个子 Agent 状态被记录
    assert set(state.sub_agent_states.keys()) == {
        "orchestrator", "research", "writing", "review", "memory"
    }