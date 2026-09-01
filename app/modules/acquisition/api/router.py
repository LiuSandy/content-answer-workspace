"""Phase 2 主动感知 API 路由。"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.database.session import get_db_session, get_session_factory
from app.modules.acquisition.application.opportunities import OpportunityService

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


class AgentSettingsRequest(BaseModel):
    workspace_id: str = Field("default", alias="workspaceId")
    proactive_sensing_enabled: bool | None = Field(None, alias="proactiveSensingEnabled")
    interest_tags: list[str] | None = Field(None, alias="interestTags")
    push_time_window: dict | None = Field(None, alias="pushTimeWindow")
    scan_interval_hours: int | None = Field(None, alias="scanIntervalHours")
    model_config = {"populate_by_name": True}


@router.get("")
async def list_opportunities(
    workspace_id: str = "default",
    limit: int = 3,
):
    factory = get_session_factory()
    async with factory() as s:
        svc = OpportunityService(s)
        items = await svc.list_top_opportunities(workspace_id, limit)

    return {
        "ok": True,
        "data": [
            {
                "id": str(it.id),
                "platform": it.platform,
                "questionTitle": it.question_title,
                "questionUrl": it.question_url,
                "hotScore": it.hot_score,
                "matchScore": it.match_score,
                "opportunityScore": it.opportunity_score,
                "existingAnswerCount": it.existing_answer_count,
                "scannedAt": it.scanned_at.isoformat() if it.scanned_at else None,
                "llmScore": it.llm_score,
                "llmReason": it.llm_reason,
                "userMatchReason": it.user_match_reason,
                "llmEvaluated": it.llm_evaluated,
            }
            for it in items
        ],
    }


@router.post("/{opportunity_id}/start-plan")
async def start_plan_from_opportunity(opportunity_id: uuid.UUID, workspace_id: str = "default"):
    """一键拉起 TaskPlan：用机会标题作为创作目标交给 TaskPlanner 规划执行（spec 2.5）"""
    from app.modules.writing.application.planning import TaskPlannerService

    factory = get_session_factory()
    async with factory() as s:
        svc = OpportunityService(s)
        items = await svc.list_top_opportunities(workspace_id, limit=20)
        target = next((it for it in items if it.id == opportunity_id), None)
        if target is None:
            raise HTTPException(status_code=404, detail="opportunity not found")

        # 把机会问题作为复合创作目标交给 planner
        planner = TaskPlannerService(s)
        plan = await planner.create_plan(
            user_instruction=f"基于该机会话题撰写一篇高质量回答：{target.question_title}",
            workspace_id=workspace_id,
            source_url=target.question_url,
        )
        return {
            "ok": True,
            "data": {
                "opportunityId": str(opportunity_id),
                "planId": str(plan.id),
                "status": plan.status,
                "subTaskCount": len(plan.sub_tasks),
            },
        }


@router.get("/stream")
async def stream_opportunities(workspace_id: str = "default", interval: int = 30):
    """SSE 推送：每隔 interval 秒推送最新 top 机会；spec 2.7 主动感知推送通道。

    客户端用 EventSource 连接；服务端持续推送直到客户端断开。
    """
    factory = get_session_factory()

    async def _generator() -> AsyncIterator[str]:
        while True:
            try:
                async with factory() as s:
                    svc = OpportunityService(s)
                    items = await svc.list_top_opportunities(workspace_id, limit=3)
                    payload = {
                        "opportunities": [
                            {
                                "id": str(it.id),
                                "platform": it.platform,
                                "questionTitle": it.question_title,
                                "questionUrl": it.question_url,
                                "hotScore": it.hot_score,
                                "matchScore": it.match_score,
                                "opportunityScore": it.opportunity_score,
                                "existingAnswerCount": it.existing_answer_count,
                            }
                            for it in items
                        ]
                    }
                    yield f"event: opportunities\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agent-settings")
async def get_agent_settings(workspace_id: str = "default"):
    from sqlalchemy import select
    from app.modules.acquisition.adapters.db.opportunity_models import AgentSettingsModel
    from app.platform.database.session import get_session_factory

    factory = get_session_factory()
    async with factory() as s:
        stmt = select(AgentSettingsModel).where(AgentSettingsModel.workspace_id == workspace_id)
        settings = (await s.execute(stmt)).scalar_one_or_none()
        if settings is None:
            return {"ok": True, "data": {
                "proactiveSensingEnabled": True,
                "interestTags": [],
                "pushTimeWindow": {},
                "scanIntervalHours": 1,
            }}
        return {"ok": True, "data": {
            "proactiveSensingEnabled": settings.proactive_sensing_enabled == "true",
            "interestTags": list(settings.interest_tags or []),
            "pushTimeWindow": dict(settings.push_time_window or {}),
            "scanIntervalHours": settings.scan_interval_hours,
        }}


@router.put("/agent-settings")
async def update_agent_settings(req: AgentSettingsRequest):
    from sqlalchemy import select
    from app.modules.acquisition.adapters.db.opportunity_models import AgentSettingsModel
    from app.platform.database.session import get_session_factory

    factory = get_session_factory()
    async with factory() as s:
        stmt = select(AgentSettingsModel).where(AgentSettingsModel.workspace_id == req.workspace_id)
        settings = (await s.execute(stmt)).scalar_one_or_none()
        if settings is None:
            settings = AgentSettingsModel(workspace_id=req.workspace_id)
            s.add(settings)
        if req.proactive_sensing_enabled is not None:
            settings.proactive_sensing_enabled = "true" if req.proactive_sensing_enabled else "false"
        if req.interest_tags is not None:
            settings.interest_tags = req.interest_tags
        if req.push_time_window is not None:
            settings.push_time_window = req.push_time_window
        if req.scan_interval_hours is not None:
            settings.scan_interval_hours = req.scan_interval_hours
        await s.commit()

    return {"ok": True, "data": {"updated": True}}


# ── R8 手动重评 ──────────────────────────────────────────────────────────


@router.post("/{opportunity_id}/re-evaluate")
async def re_evaluate_opportunity(opportunity_id: str):
    from app.modules.acquisition.application.topic_analyst import TopicAnalystService
    from app.platform.database.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        svc = TopicAnalystService(session)
        result = await svc.re_evaluate(opportunity_id)
        if result is None:
            return {"ok": False, "error": "Not found or evaluation failed"}
        return {"ok": True, "data": result}