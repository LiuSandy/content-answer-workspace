"""Phase 3 自主规划引擎；spec 2.3 节。

PlannerNode: LLM 拆解用户目标为 5 步以上 DAG SubTask 列表
TaskExecutorGraph: 并行调度 Subset，根据 depends_on 拓扑排序
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from app.contracts.errors import LLMOutputError

logger = logging.getLogger(__name__)

SubTaskType = Literal["search", "analyze", "outline", "write", "review"]


@dataclass
class SubTask:
    task_id: str
    type: SubTaskType
    description: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class TaskPlan:
    plan_id: str
    goal: str
    tasks: list[SubTask]
    status: str = "pending"


VALID_TYPES = {"search", "analyze", "outline", "write", "review"}


def _parse_plan_json(content: str, goal: str) -> TaskPlan:
    """从 LLM 输出解析 TaskPlan，校验 type、依赖图无环。"""
    try:
        if "{" in content:
            json_str = content[content.index("{"): content.rindex("}") + 1]
            data = json.loads(json_str)
        else:
            raise ValueError("No JSON object in planner output")
    except (json.JSONDecodeError, ValueError) as e:
        raise LLMOutputError(f"TaskPlan JSON 解析失败: {e}") from e

    tasks_raw = data.get("tasks") or []
    if not tasks_raw or len(tasks_raw) < 5:
        raise LLMOutputError(f"TaskPlan 必须包含至少 5 个子任务，实际 {len(tasks_raw)}")

    plan_id = str(uuid.uuid4())
    tasks = []
    task_ids = set()
    for t in tasks_raw:
        tid = t.get("task_id") or t.get("id") or ""
        typ = t.get("type", "")
        if typ not in VALID_TYPES:
            raise LLMOutputError(f"未知 SubTask type: {typ}")
        desc = t.get("description", "")
        deps = list(t.get("depends_on") or [])
        if not tid or not desc:
            raise LLMOutputError("SubTask 缺少 task_id 或 description")
        task_ids.add(tid)
        tasks.append(SubTask(task_id=tid, type=typ, description=desc, depends_on=deps))

    # 拓扑排序校验无环 + 依赖 task_id 存在
    _validate_dag(tasks, task_ids)

    return TaskPlan(plan_id=plan_id, goal=goal, tasks=tasks, status="pending")


def _validate_dag(tasks: list[SubTask], task_ids: set[str]) -> None:
    """校验 depend_on 引用存在 + 无环。"""
    for t in tasks:
        for dep in t.depends_on:
            if dep not in task_ids:
                raise LLMOutputError(f"SubTask {t.task_id} 依赖未知 task_id: {dep}")

    # 拓扑排序
    visited: dict[str, int] = {}  # 0=visiting, 1=done

    def visit(tid: str):
        st = visited.get(tid)
        if st == 1:
            return
        if st == 0:
            raise LLMOutputError(f"TaskPlan 存在环，涉及 task_id: {tid}")
        visited[tid] = 0
        t = next(x for x in tasks if x.task_id == tid)
        for dep in t.depends_on:
            visit(dep)
        visited[tid] = 1

    for t in tasks:
        visit(t.task_id)


def _get_planner_llm():
    from app.services.llm_service import LLMServiceAdapter
    return LLMServiceAdapter()


async def generate_plan(goal: str) -> TaskPlan:
    """调用 LLM 把目标拆解为 5 步以上 TaskPlan。"""
    from ..prompts.registry import prompt_registry
    rendered = prompt_registry.render("planning.planner", goal=goal)
    messages = rendered.to_llm_request().messages
    system_prompt = messages[0].content if messages else ""
    user_prompt = messages[1].content if len(messages) > 1 else goal

    llm = _get_planner_llm()
    raw = await llm.analyze(system_prompt, user_prompt)
    return _parse_plan_json(raw, goal)


def topological_order(plan: TaskPlan) -> list[list[SubTask]]:
    """按拓扑序返回分层子任务列表；同一层可并行执行。"""
    layers: list[list[SubTask]] = []
    done: set[str] = set()

    remaining = list(plan.tasks)
    while remaining:
        layer = [t for t in remaining if all(d in done for d in t.depends_on)]
        if not layer:
            # 理论上 _validate_dag 已保证无环，防御性兜底
            raise LLMOutputError("TaskPlan DAG 拓扑排序失败")
        layers.append(layer)
        done.update(t.task_id for t in layer)
        remaining = [t for t in remaining if t.task_id not in done]
    return layers


async def execute_subtask(subtask: SubTask, prior_results: dict[str, str]) -> str:
    """执行单个子任务，返回结果文本。

    Phase 3 第一版只实现 search/outline/write/review 各自的 LLM 调用模式：
    - search 调用 web_search 工具（此处简化为 LLM 直出查询摘要）
    - analyze 用 LLM 分析前序结果
    - outline / write / review 用对应 prompt
    """
    deps_summary = "\n".join(
        f"[{tid}]: {text}" for tid, text in prior_results.items() if tid in subtask.depends_on
    )

    from ..prompts.registry import prompt_registry
    prompt_id = f"planning.{subtask.type}_subtask"
    try:
        rendered = prompt_registry.render(
            prompt_id,
            description=subtask.description,
            depends_on=deps_summary or "无",
            goal="",  # 由 planner service 在更上层拼入
        )
        messages = rendered.to_llm_request().messages
        system_prompt = messages[0].content if messages else subtask.description
        user_prompt = messages[1].content if len(messages) > 1 else subtask.description
        llm = _get_planner_llm()
        result = await llm.analyze(system_prompt, user_prompt)
        return result
    except Exception as e:
        logger.warning("Subtask prompt %s not available, falling back: %s", prompt_id, e)
        llm = _get_planner_llm()
        return await llm.analyze(
            f"你是 {subtask.type} 子任务执行者。",
            f"任务：{subtask.description}\n\n依赖结果:\n{deps_summary}",
        )


async def execute_task_plan(plan: TaskPlan) -> dict[str, str]:
    """按 DAG 并行执行整个 plan，返回 task_id → result。

    失败的子任务不阻断已完成；返回 dict 只含完成的结果。
    """
    layers = topological_order(plan)
    results: dict[str, str] = {}

    for layer in layers:
        async def _exec_one(t: SubTask) -> tuple[str, str | None]:
            try:
                r = await execute_subtask(t, results)
                return t.task_id, r
            except Exception as e:
                logger.error("Subtask %s failed: %s", t.task_id, e)
                return t.task_id, None

        layer_results = await asyncio.gather(*(_exec_one(t) for t in layer))
        for tid, r in layer_results:
            if r is not None:
                results[tid] = r

    return results
