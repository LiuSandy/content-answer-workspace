"""Phase 4 多 Agent API 路由测试。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.server import app
from app.agents.orchestrator.state import MultiAgentState, SubAgentState
from app.services.planning_service import TaskPlan


def _make_client():
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _fake_state(agents_status: dict[str, str]) -> MultiAgentState:
    subs = {
        name: SubAgentState(
            name=name,
            status=status,
            result=f"result-of-{name}",
        )
        for name, status in agents_status.items()
    }
    return MultiAgentState(
        plan=TaskPlan(plan_id="p1", goal="目标", tasks=[]),
        sub_agent_states=subs,
        final_output="final-content",
    )


@pytest.mark.asyncio
@patch("app.agents.orchestrator.graph.run_multi_agent_plan")
async def test_run_multi_agent_success(mock_run):
    mock_run.return_value = _fake_state({
        "orchestrator": "done",
        "research": "done",
        "writing": "done",
        "review": "done",
        "memory": "done",
    })
    async with _make_client() as client:
        res = await client.post("/api/multi-agent/run", json={
            "goal": "写一篇关于 RAG 的文章",
            "workspaceId": "default",
        })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "done"
    assert len(data["agents"]) == 5
    assert data["finalContent"] == "final-content"


@pytest.mark.asyncio
@patch("app.agents.orchestrator.graph.run_multi_agent_plan")
async def test_run_multi_agent_accepts_real_orchestrator_state(mock_run):
    mock_run.return_value = MultiAgentState(
        plan=TaskPlan(plan_id="p1", goal="目标", tasks=[]),
        sub_agent_states={
            "orchestrator": SubAgentState(
                name="orchestrator",
                status="done",
                result={"total_tasks": 0},
            ),
            "writing": SubAgentState(
                name="writing",
                status="done",
                result={"chars": 5},
            ),
        },
        draft="初稿",
        final_output="最终内容",
    )

    async with _make_client() as client:
        res = await client.post("/api/multi-agent/run", json={"goal": "目标"})

    assert res.status_code == 200
    assert res.json()["data"] == {
        "status": "done",
        "agents": [
            {"name": "orchestrator", "status": "done", "message": None},
            {"name": "writing", "status": "done", "message": None},
        ],
        "finalContent": "最终内容",
    }


@pytest.mark.asyncio
@patch("app.agents.orchestrator.graph.run_multi_agent_plan")
async def test_run_multi_agent_has_required_agents(mock_run):
    mock_run.return_value = _fake_state({
        "orchestrator": "done",
        "research": "done",
        "writing": "done",
        "review": "done",
        "memory": "done",
    })
    async with _make_client() as client:
        res = await client.post("/api/multi-agent/run", json={"goal": "目标"})
    assert res.status_code == 200
    names = {a["name"] for a in res.json()["data"]["agents"]}
    assert names == {"orchestrator", "research", "writing", "review", "memory"}


@pytest.mark.asyncio
@patch("app.agents.orchestrator.graph.run_multi_agent_plan")
async def test_run_multi_agent_failure_is_isolated(mock_run):
    mock_run.return_value = _fake_state({
        "orchestrator": "done",
        "research": "failed",
        "writing": "done",
        "review": "done",
        "memory": "done",
    })
    async with _make_client() as client:
        res = await client.post("/api/multi-agent/run", json={"goal": "目标"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "failed"
    by_name = {a["name"]: a["status"] for a in data["agents"]}
    assert by_name["research"] == "failed"


@pytest.mark.asyncio
@patch("app.agents.orchestrator.graph.run_multi_agent_plan")
async def test_run_multi_agent_internal_error(mock_run):
    mock_run.side_effect = RuntimeError("boom")
    async with _make_client() as client:
        res = await client.post("/api/multi-agent/run", json={"goal": "目标"})
    assert res.status_code == 500


@pytest.mark.asyncio
async def test_interrupt_resume_flow():
    async with _make_client() as client:
        # interrupt
        res = await client.post("/api/multi-agent/{}/interrupt".format("some-run-id"))
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "interrupt_requested"

        # resume
        res = await client.post("/api/multi-agent/{}/resume".format("some-run-id"))
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "resumed"
