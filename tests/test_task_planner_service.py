"""Phase 3 · Task 12-15：PlannerNode + DAG 校验 + ExecutorGraph 测试。"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.task_planner_service import (
    SubTask, TaskPlan, _parse_plan_json, _validate_dag, topological_order,
    execute_subtask, execute_task_plan,
)
from app.errors import LLMOutputError


def _valid_plan_json():
    return """{
      "tasks": [
        {"task_id": "t1", "type": "search", "description": "搜索资料", "depends_on": []},
        {"task_id": "t2", "type": "analyze", "description": "分析", "depends_on": ["t1"]},
        {"task_id": "t3", "type": "outline", "description": "提纲", "depends_on": ["t2"]},
        {"task_id": "t4", "type": "write", "description": "写作", "depends_on": ["t3"]},
        {"task_id": "t5", "type": "review", "description": "自评", "depends_on": ["t4"]}
      ]
    }"""


def test_parse_valid_plan():
    plan = _parse_plan_json(_valid_plan_json(), "写一篇")
    assert len(plan.tasks) == 5
    assert plan.tasks[0].task_id == "t1"
    assert plan.tasks[1].depends_on == ["t1"]


def test_parse_rejects_too_few_tasks():
    """spec 2.6: 5 步以上。"""
    too_few = '{"tasks": [{"task_id": "t1", "type": "search", "description": "x", "depends_on": []}]}'
    with pytest.raises(LLMOutputError):
        _parse_plan_json(too_few, "x")


def test_parse_rejects_invalid_type():
    """spec 2.6: 5 步以上。"""
    bad = '''{"tasks": [
      {"task_id": "t1", "type": "FOO", "description": "x", "depends_on": []},
      {"task_id": "t2", "type": "search", "description": "x", "depends_on": []},
      {"task_id": "t3", "type": "search", "description": "x", "depends_on": []},
      {"task_id": "t4", "type": "search", "description": "x", "depends_on": []},
      {"task_id": "t5", "type": "search", "description": "x", "depends_on": []}
    ]}'''
    with pytest.raises(LLMOutputError):
        _parse_plan_json(bad, "x")


def test_dag_rejects_cycle():
    cyclic = '''{"tasks": [
      {"task_id": "t1", "type": "search", "description": "x", "depends_on": ["t2"]},
      {"task_id": "t2", "type": "search", "description": "x", "depends_on": ["t1"]},
      {"task_id": "t3", "type": "search", "description": "x", "depends_on": ["t1"]},
      {"task_id": "t4", "type": "search", "description": "x", "depends_on": ["t3"]},
      {"task_id": "t5", "type": "search", "description": "x", "depends_on": ["t4"]}
    ]}'''
    with pytest.raises(LLMOutputError):
        _parse_plan_json(cyclic, "x")


def test_dag_rejects_unknown_dependency():
    unknown = '''{"tasks": [
      {"task_id": "t1", "type": "search", "description": "x", "depends_on": ["ghost"]},
      {"task_id": "t2", "type": "search", "description": "x", "depends_on": []},
      {"task_id": "t3", "type": "search", "description": "x", "depends_on": []},
      {"task_id": "t4", "type": "search", "description": "x", "depends_on": []},
      {"task_id": "t5", "type": "search", "description": "x", "depends_on": []}
    ]}'''
    with pytest.raises(LLMOutputError):
        _parse_plan_json(unknown, "x")


def test_topological_order_separates_layers():
    plan = TaskPlan(
        plan_id="p1", goal="x",
        tasks=[
            SubTask("t1", "search", "s", []),
            SubTask("t2", "search", "s", []),
            SubTask("t3", "analyze", "a", ["t1", "t2"]),
            SubTask("t4", "write", "w", ["t3"]),
        ],
    )
    layers = topological_order(plan)
    assert len(layers) == 3
    assert {t.task_id for t in layers[0]} == {"t1", "t2"}
    assert {t.task_id for t in layers[1]} == {"t3"}
    assert {t.task_id for t in layers[2]} == {"t4"}


@pytest.mark.asyncio
async def test_execute_subtask_falls_back_when_prompt_missing(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(return_value="fallback result")
    monkeypatch.setattr(
        "app.application.task_planner_service._get_planner_llm",
        lambda: fake_llm,
    )
    # 不预热 prompt registry，触发异常回退分支
    sub = SubTask("t1", "search", "搜索资料", [])
    r = await execute_subtask(sub, {})
    assert r == "fallback result"


@pytest.mark.asyncio
async def test_execute_task_plan_parallel_layer(monkeypatch):
    """同层无依赖任务并行执行。"""
    call_times = []

    async def fake_execute(subtask, prior):
        call_times.append((subtask.task_id, asyncio.get_event_loop().time()))
        await asyncio.sleep(0.01)
        return f"result-{subtask.task_id}"

    monkeypatch.setattr(
        "app.application.task_planner_service.execute_subtask",
        fake_execute,
    )

    plan = TaskPlan(
        plan_id="p1", goal="",
        tasks=[
            SubTask("t1", "search", "x", []),
            SubTask("t2", "search", "x", []),
            SubTask("t3", "analyze", "x", ["t1", "t2"]),
        ],
    )
    results = await execute_task_plan(plan)
    assert results == {"t1": "result-t1", "t2": "result-t2", "t3": "result-t3"}
    # t1, t2 同时刻启动（差 < 5ms）
    t1, t2 = call_times[0][1], call_times[1][1]
    assert abs(t1 - t2) < 0.005