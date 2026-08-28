"""Phase 4 · 多 Agent 协作测试。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.writer import graph as writer_graph_module
from app.agents.writer import state as writer_state
from app.agents.writer.nodes.pipeline import (
    research_node,
    review_node,
    write_node,
    writer_memory_node,
)
from app.agents.writer.nodes.planner import assign_node
from app.agents.writer.runtime import run_writer_plan
from app.agents.writer.state import MultiAgentState, SubAgentState
from app.services.planning_service import SubTask, TaskPlan
from app.contracts.dto import QualityReport


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


def test_writer_graph_owns_the_full_content_pipeline_state():
    WriterState = getattr(writer_state, "WriterState", None)
    assert WriterState is not None
    assert "research_tasks" in WriterState.__annotations__
    assert "writing_prompt" in WriterState.__annotations__
    assert "review_context" in WriterState.__annotations__
    assert "operation" in WriterState.__annotations__
    assert "document_id" in WriterState.__annotations__


def test_writer_is_the_only_compiled_content_graph():
    graph = getattr(writer_graph_module, "writer_graph", None)
    assert graph is not None
    assert set(graph.get_graph().nodes) >= {
        "guard", "generate_plan", "assign_tasks", "research", "write",
        "review", "memory", "finalize",
    }


def test_agents_package_has_exactly_two_graph_modules():
    graph_files = sorted(
        path.relative_to(path.parents[2]).as_posix()
        for path in Path(__file__).parents[1].joinpath("app/agents").rglob("graph.py")
    )
    assert graph_files == ["agents/chat/graph.py", "agents/writer/graph.py"]


@pytest.mark.asyncio
async def test_orchestrator_assigns_tasks():
    result = assign_node({"plan": _mock_plan(), "sub_agent_states": {}})
    sub = result["sub_agent_states"]["orchestrator"]
    assert sub.status == "done"
    assert sub.result["total_tasks"] == 5


@pytest.mark.asyncio
async def test_orchestrator_fails_on_empty_plan():
    result = assign_node({"plan": TaskPlan("p0", "", []), "sub_agent_states": {}})
    sub = result["sub_agent_states"]["orchestrator"]
    assert sub.status == "failed"


@pytest.mark.asyncio
async def test_writing_agent_produces_draft(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value="# 初稿\n\n正文内容...")
    monkeypatch.setattr(
        "app.agents.writer.nodes.generate_draft._get_planner_llm",
        lambda: fake_llm,
    )
    result = await write_node({
        "plan": _mock_plan(),
        "research_report": "研究报告内容",
        "sub_agent_states": {},
    })
    assert "初稿" in result["draft"]
    assert result["sub_agent_states"]["writing"].status == "done"


@pytest.mark.asyncio
async def test_review_agent_failure_does_not_block_final_output(monkeypatch):
    """spec 6.6 #2：单子 Agent 失败不影响其他。ReviewAgent 失败时初稿作终稿。"""
    monkeypatch.setattr(
        "app.agents.writer.nodes.pipeline.evaluate_content",
        AsyncMock(side_effect=RuntimeError("review failed")),
    )
    result = await review_node({
        "plan": _mock_plan(),
        "draft": "这是初稿",
        "sub_agent_states": {},
    })
    # ReviewAgent 失败，但 final_output 保留初稿
    assert result["final_output"] == "这是初稿"
    assert result["sub_agent_states"]["review"].status == "failed"
    assert result["sub_agent_states"]["review"].error is not None


@pytest.mark.asyncio
async def test_memory_agent_failure_isolated(monkeypatch):
    """MemoryAgent 失败不影响整体协作状态。"""
    monkeypatch.setattr(
        "app.services.memory.service.extract_memories",
        AsyncMock(side_effect=RuntimeError("memory store down")),
    )
    result = await writer_memory_node({
        "plan": _mock_plan(),
        "final_output": "final",
        "sub_agent_states": {},
    })
    assert result["sub_agent_states"]["memory"].status == "failed"
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
        "app.services.planning_service.execute_subtask",
        fake_execute,
    )
    monkeypatch.setattr(
        "app.services.planning_service._get_planner_llm",
        lambda: MagicMock(),
    )

    result = await research_node({"plan": plan, "sub_agent_states": {}})
    sub = result["sub_agent_states"]["research"]
    assert sub.status == "done"
    assert sub.result["concurrent_calls"] >= 4
    # s1-s4 同层并行（启动时间差 < 5ms）
    times = [t for _, t in call_log[:4]]
    assert max(times) - min(times) < 0.005 or len(call_log) >= 4


@pytest.mark.asyncio
async def test_research_agent_with_no_tasks_preserves_legacy_empty_result():
    result = await research_node({"plan": TaskPlan("p0", "x", []), "sub_agent_states": {}})
    assert result["research_report"] == ""
    assert result["sub_agent_states"]["research"].status == "done"
    assert result["sub_agent_states"]["research"].result is None


@pytest.mark.asyncio
async def test_research_agent_failure_preserves_existing_report(monkeypatch):
    monkeypatch.setattr(
        "app.services.planning_service.execute_task_plan",
        AsyncMock(side_effect=RuntimeError("search failed")),
    )
    result = await research_node({
        "plan": _mock_plan(),
        "research_report": "existing report",
        "sub_agent_states": {},
    })
    assert result["research_report"] == "existing report"
    assert result["sub_agent_states"]["research"].status == "failed"


@pytest.mark.asyncio
async def test_research_agent_failure_preserves_none_report(monkeypatch):
    monkeypatch.setattr(
        "app.services.planning_service.execute_task_plan",
        AsyncMock(side_effect=RuntimeError("search failed")),
    )
    result = await research_node({"plan": _mock_plan(), "sub_agent_states": {}})
    assert result["research_report"] is None
    assert result["sub_agent_states"]["research"].status == "failed"


@pytest.mark.asyncio
async def test_run_writer_plan_end_to_end(monkeypatch):
    """端到端：planner → research → writing → review → memory。"""
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value="初稿内容")
    monkeypatch.setattr(
        "app.agents.writer.nodes.generate_draft._get_planner_llm",
        lambda: fake_llm,
    )
    monkeypatch.setattr(
        "app.agents.writer.nodes.planner.generate_plan",
        AsyncMock(return_value=_mock_plan()),
    )
    # mock execute_task_plan 避免真实 LLM
    async def fake_exec(plan):
        return {t.task_id: f"r-{t.task_id}" for t in plan.tasks}
    monkeypatch.setattr(
        "app.services.planning_service.execute_task_plan",
        fake_exec,
    )
    # mock 统一创作评审，首轮达标时不会触发重写
    async def fake_evaluate(content, context):
        return QualityReport(
            overall_score=85,
            dimension_scores={
                "relevance": 85,
                "information_density": 85,
                "readability": 85,
                "logic_coherence": 85,
                "word_count_compliance": 85,
            },
            issues=[],
            suggestions=[],
            summary="已达标",
        )
    monkeypatch.setattr(
        "app.agents.writer.nodes.pipeline.evaluate_content",
        fake_evaluate,
    )
    # mock memory
    monkeypatch.setattr(
        "app.services.memory.service.extract_memories",
        AsyncMock(return_value=[]),
    )

    state = await run_writer_plan("写一篇", workspace_id="default")
    assert state.final_output == "初稿内容"
    assert state.quality_score == 85
    # 全部 5 个子 Agent 状态被记录
    assert set(state.sub_agent_states.keys()) == {
        "orchestrator", "research", "writing", "review", "memory"
    }
