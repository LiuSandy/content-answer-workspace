"""Phase 3 TaskPlan REST API。"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...persistence.session import get_session_factory
from ...persistence.models.task_plans import TaskPlanModel, SubTaskModel
from ...application.task_planner_service import (
    generate_plan, execute_task_plan, TaskPlan, _validate_dag, _parse_plan_json,
    execute_subtask,
)
from ..sse_utils import sse_named_event, make_sse_response
from ...observability.context import reset_log_context, set_log_context

router = APIRouter(prefix="/api/task-plans", tags=["task-plans"])


class CreateTaskPlanRequest(BaseModel):
    goal: str
    chat_id: str | None = Field(None, alias="chatId")
    workspace_id: str = Field("default", alias="workspaceId")
    model_config = {"populate_by_name": True}


class RetryTaskRequest(BaseModel):
    pass


@router.post("")
async def create_task_plan(req: CreateTaskPlanRequest):
    """生成 TaskPlan 并落库，返回 plan 概要。执行由 /stream 端点 SSE 推送。"""
    plan = await generate_plan(req.goal)

    factory = get_session_factory()
    async with factory() as session:
        plan_row = TaskPlanModel(
            workspace_id=req.workspace_id,
            chat_id=uuid.UUID(req.chat_id) if req.chat_id else None,
            goal=req.goal,
            status="pending",
        )
        session.add(plan_row)
        await session.flush()
        for t in plan.tasks:
            sub = SubTaskModel(
                plan_id=plan_row.id,
                task_id=t.task_id,
                type=t.type,
                description=t.description,
                depends_on=t.depends_on,
            )
            session.add(sub)
        await session.commit()
        plan_id = str(plan_row.id)

    return {
        "ok": True,
        "data": {
            "planId": plan_id,
            "goal": req.goal,
            "status": "pending",
            "tasks": [
                {"taskId": t.task_id, "type": t.type, "description": t.description, "dependsOn": t.depends_on, "status": "pending"}
                for t in plan.tasks
            ],
        },
    }


@router.get("/{plan_id}")
async def get_task_plan(plan_id: str):
    factory = get_session_factory()
    async with factory() as session:
        plan_row = await session.get(TaskPlanModel, uuid.UUID(plan_id))
        if not plan_row:
            raise HTTPException(status_code=404, detail="TaskPlan not found")
        stmt = (
            select(SubTaskModel)
            .where(SubTaskModel.plan_id == plan_row.id)
            .order_by(SubTaskModel.task_id)
        )
        subs = list((await session.execute(stmt)).scalars().all())
        return {
            "ok": True,
            "data": {
                "planId": str(plan_row.id),
                "goal": plan_row.goal,
                "status": plan_row.status,
                "tasks": [
                    {
                        "taskId": s.task_id, "type": s.type,
                        "description": s.description, "dependsOn": s.depends_on,
                        "status": s.status, "result": s.result,
                    }
                    for s in subs
                ],
            },
        }


async def _to_plan(plan_row, subs) -> TaskPlan:
    from ...application.task_planner_service import SubTask as _Sub
    tasks = [
        _Sub(task_id=s.task_id, type=s.type, description=s.description, depends_on=list(s.depends_on or []))
        for s in subs
    ]
    return TaskPlan(plan_id=str(plan_row.id), goal=plan_row.goal, tasks=tasks)


@router.post("/{plan_id}/stream")
async def stream_task_plan(plan_id: str, req: CreateTaskPlanRequest = Body(default=None)):  # type: ignore
    """SSE 推送 plan 执行进度。"""
    factory = get_session_factory()

    async def _gen():
        run_id = str(uuid.uuid4())
        log_token = set_log_context(run_id=run_id, plan_id=plan_id)
        yield sse_named_event("run.started", {"runId": run_id, "planId": plan_id})
        try:
            async with factory() as session:
                plan_row = await session.get(TaskPlanModel, uuid.UUID(plan_id))
                if not plan_row:
                    yield sse_named_event("run.failed", {"error": "TaskPlan not found"})
                    return
                stmt = select(SubTaskModel).where(SubTaskModel.plan_id == plan_row.id)
                subs = list((await session.execute(stmt)).scalars().all())
                plan = await _to_plan(plan_row, subs)
                plan_row.status = "running"
                await session.commit()

            from ...application.task_planner_service import topological_order
            layers = topological_order(plan)
            results: dict[str, str] = {}

            for layer in layers:
                yield sse_named_event("layer.started", {"taskIds": [t.task_id for t in layer]})
                async with factory() as s_check:
                    cur = await s_check.get(TaskPlanModel, plan_row.id)
                    if cur and cur.status == "interrupted":
                        yield sse_named_event("plan.interrupted", {"planId": plan_id})
                        return
                layer_results = await asyncio.gather(*(_run_one_no_yield(t, plan_row.id, results) for t in layer))
                for tid, status, preview_or_err in layer_results:
                    if status == "done":
                        yield sse_named_event("task.completed", {"taskId": tid, "resultPreview": preview_or_err[:200]})
                    else:
                        yield sse_named_event("task.failed", {"taskId": tid, "error": preview_or_err})
                yield sse_named_event("layer.completed", {"taskIds": [t.task_id for t in layer]})

            async with factory() as s5:
                plan_row = await s5.get(TaskPlanModel, plan_row.id)
                if plan_row:
                    plan_row.status = "done"
                    await s5.commit()
            yield sse_named_event("plan.completed", {"planId": plan_id})
        finally:
            reset_log_context(log_token)

    return make_sse_response(_gen)


async def _run_one_no_yield(sub_task, plan_id: uuid.UUID, results: dict):
    """并行执行单 subtask，返回 (task_id, status, preview_or_err)；不做 yield。"""
    from ...application.task_planner_service import execute_subtask
    factory = get_session_factory()
    log_token = set_log_context(plan_id=str(plan_id), task_id=sub_task.task_id)
    try:
        async with factory() as s:
            sub_row = (await s.execute(
                select(SubTaskModel).where(
                    SubTaskModel.plan_id == plan_id,
                    SubTaskModel.task_id == sub_task.task_id,
                ).limit(1)
            )).scalar_one_or_none()
            if sub_row:
                sub_row.status = "running"
                await s.commit()

        r = await execute_subtask(sub_task, results)
        results[sub_task.task_id] = r
        async with factory() as s2:
            sub_row = (await s2.execute(
                select(SubTaskModel).where(
                    SubTaskModel.plan_id == plan_id,
                    SubTaskModel.task_id == sub_task.task_id,
                ).limit(1)
            )).scalar_one_or_none()
            if sub_row:
                sub_row.status = "done"
                sub_row.result = r
                await s2.commit()
        return sub_task.task_id, "done", r
    except Exception as e:
        async with factory() as s3:
            sub_row = (await s3.execute(
                select(SubTaskModel).where(
                    SubTaskModel.plan_id == plan_id,
                    SubTaskModel.task_id == sub_task.task_id,
                ).limit(1)
            )).scalar_one_or_none()
            if sub_row:
                sub_row.status = "failed"
                await s3.commit()
        return sub_task.task_id, "failed", str(e)
    finally:
        reset_log_context(log_token)


@router.post("/{plan_id}/tasks/{task_id}/retry")
async def retry_task(plan_id: str, task_id: str, _req: RetryTaskRequest = Body(default=None)):  # type: ignore
    """单子任务失败重试；不重新生成 plan，仅重跑指定 subtask。"""
    factory = get_session_factory()
    async with factory() as session:
        plan_row = await session.get(TaskPlanModel, uuid.UUID(plan_id))
        if not plan_row:
            raise HTTPException(status_code=404, detail="TaskPlan not found")
        stmt = select(SubTaskModel).where(
            SubTaskModel.plan_id == plan_row.id,
            SubTaskModel.task_id == task_id,
        ).limit(1)
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=404, detail="SubTask not found")

        # 收集依赖结果
        deps_results: dict[str, str] = {}
        for dep_id in sub.depends_on or []:
            dep_stmt = select(SubTaskModel).where(
                SubTaskModel.plan_id == plan_row.id,
                SubTaskModel.task_id == dep_id,
            ).limit(1)
            dep = (await session.execute(dep_stmt)).scalar_one_or_none()
            if dep and dep.result:
                deps_results[dep_id] = dep.result

        from ...application.task_planner_service import SubTask as _Sub
        sub_obj = _Sub(task_id=sub.task_id, type=sub.type, description=sub.description, depends_on=list(sub.depends_on or []))
        # _run_one_no_yield 直接复用
        tid, status, preview = await _run_one_no_yield(sub_obj, plan_row.id, deps_results)
        return {"ok": True, "data": {"taskId": tid, "status": status, "preview": preview[:200] if status == "done" else preview}}


@router.post("/{plan_id}/interrupt")
async def interrupt_task_plan(plan_id: str):
    """中断任务计划：标记 plan 为 interrupted，当前执行层跑完后不再继续后续层。"""
    factory = get_session_factory()
    async with factory() as session:
        plan_row = await session.get(TaskPlanModel, uuid.UUID(plan_id))
        if not plan_row:
            raise HTTPException(status_code=404, detail="TaskPlan not found")
        plan_row.status = "interrupted"
        # 尚未开始的任务标记为 cancelled
        stmt = select(SubTaskModel).where(
            SubTaskModel.plan_id == plan_row.id,
            SubTaskModel.status.in_(["pending", "running"]),
        )
        subs = list((await session.execute(stmt)).scalars().all())
        for sub in subs:
            if sub.status == "pending":
                sub.status = "cancelled"
        await session.commit()
        return {"ok": True, "data": {"planId": plan_id, "status": "interrupted"}}


@router.post("/{plan_id}/resume")
async def resume_task_plan(plan_id: str):
    """恢复中断/失败的计划：把 cancelled/pending 的子任务恢复为 pending，重新开始执行。"""
    factory = get_session_factory()
    async with factory() as session:
        plan_row = await session.get(TaskPlanModel, uuid.UUID(plan_id))
        if not plan_row:
            raise HTTPException(status_code=404, detail="TaskPlan not found")
        if plan_row.status not in ("interrupted", "failed"):
            return {"ok": True, "data": {"planId": plan_id, "status": plan_row.status, "message": "计划未中断，无需恢复"}}
        stmt = select(SubTaskModel).where(SubTaskModel.plan_id == plan_row.id)
        subs = list((await session.execute(stmt)).scalars().all())
        for sub in subs:
            if sub.status in ("cancelled", "pending", "failed"):
                sub.status = "pending"
        plan_row.status = "pending"
        await session.commit()
        return {
            "ok": True,
            "data": {
                "planId": plan_id,
                "status": "pending",
                "message": "已恢复，可通过 /stream 端点重新执行",
            },
        }
