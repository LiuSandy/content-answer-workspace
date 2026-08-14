"""Phase 4 多 Agent 协作 API。spec 6.2 SSE 状态推送 / 6.4 interrupt/resume。"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.api.streaming.sse import sse_named_event, make_sse_response

router = APIRouter(prefix="/api/multi-agent", tags=["multi-agent"])

# 内存中的运行状态；生产可用 Redis/DB，这里先简化
_running: dict[str, dict] = {}
_interrupted: dict[str, bool] = {}


class RunMultiAgentRequest(BaseModel):
    goal: str
    workspace_id: str = Field("default", alias="workspaceId")
    model_config = {"populate_by_name": True}


def _status_payload(run_id: str, state: dict | None) -> dict:
    base = {"runId": run_id}
    if not state:
        return base
    subs = state.get("sub_agent_states", {})
    return {
        **base,
        "status": state.get("status"),
        "agents": [
            {
                "name": name,
                "status": sub.get("status"),
                "message": sub.get("message"),
                "resultPreview": (sub.get("result") or "")[:500],
            }
            for name, sub in subs.items()
        ],
        "finalContent": state.get("final_content"),
    }


@router.post("/run")
async def run_multi_agent(req: RunMultiAgentRequest):
    """同步执行多 Agent 协作流，返回最终结果。用于简单测试 / 脚本调用。"""
    from app.agents.orchestrator.graph import run_multi_agent_plan

    try:
        state = await run_multi_agent_plan(req.goal, req.workspace_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"multi-agent run failed: {e}")

    subs = state.sub_agent_states
    status = (
        "failed"
        if any(sub.status == "failed" for sub in subs.values())
        else "done"
    )
    return {
        "ok": True,
        "data": {
            "status": status,
            "agents": [
                {
                    "name": name,
                    "status": sub.status,
                    "message": sub.error,
                }
                for name, sub in subs.items()
            ],
            "finalContent": state.final_output or state.draft,
        },
    }


@router.post("/{run_id}/interrupt")
async def interrupt_multi_agent(run_id: str):
    """请求中断正在运行的 multi-agent 流（协作者完成后不继续下一阶段）。"""
    _interrupted[run_id] = True
    return {"ok": True, "data": {"runId": run_id, "status": "interrupt_requested"}}


@router.post("/{run_id}/resume")
async def resume_multi_agent(run_id: str):
    """清除中断标记，允许恢复（下次 /run 时忽略）。"""
    _interrupted.pop(run_id, None)
    return {"ok": True, "data": {"runId": run_id, "status": "resumed"}}


@router.get("/{run_id}")
async def get_multi_agent_status(run_id: str):
    """查询运行状态。"""
    state = _running.get(run_id)
    if state is None:
        return {"ok": True, "data": {"runId": run_id, "status": "not_found"}}
    return {"ok": True, "data": _status_payload(run_id, state)}


@router.get("/{run_id}/stream")
async def stream_multi_agent(run_id: str):
    """SSE 推送多 Agent 协作状态变化。客户端先 POST /run 拿到 runId，再连此端点。"""
    async def _gen() -> AsyncIterator[str]:
        yield sse_named_event("run.started", {"runId": run_id})
        while True:
            state = _running.get(run_id)
            if state:
                yield sse_named_event("agent.status", _status_payload(run_id, state))
                if state.get("status") in ("done", "failed"):
                    yield sse_named_event("run.completed", {"runId": run_id})
                    return
            if _interrupted.get(run_id):
                yield sse_named_event("run.interrupted", {"runId": run_id})
                return
            await asyncio.sleep(1)

    return make_sse_response(_gen)
