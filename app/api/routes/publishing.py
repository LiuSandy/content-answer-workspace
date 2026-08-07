"""发布 API：draft→ready→published 状态转换 + 手动指标 CRUD（roadmap R10）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...persistence.session import get_session_factory
from ...persistence.models.documents import AnswerDocument
from ...persistence.models.publish_metrics import PublishMetricsModel

router = APIRouter(prefix="/api/publishing", tags=["publishing"])


class SetPublishStatusRequest(BaseModel):
    status: str  # ready | published
    url: str | None = None  # 发布 URL（published 时）
    workspace_id: str = Field("default", alias="workspaceId")
    model_config = {"populate_by_name": True}


class MetricsRequest(BaseModel):
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    collects: int | None = None
    label: str | None = None


@router.put("/documents/{document_id}/publish-status")
async def set_publish_status(document_id: uuid.UUID, req: SetPublishStatusRequest):
    factory = get_session_factory()
    async with factory() as session:
        doc = await session.get(AnswerDocument, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.publish_status == req.status:
            return {"ok": True, "data": {"status": doc.publish_status, "unchanged": True}}
        if doc.publish_status == "draft" and req.status != "ready":
            raise HTTPException(status_code=400, detail="draft can only transition to ready")
        if doc.publish_status == "ready" and req.status != "published":
            raise HTTPException(status_code=400, detail="Only ready→published allowed")

        doc.publish_status = req.status
        if req.url:
            doc.publish_url = req.url
        if req.status == "published":
            from datetime import datetime, timezone
            doc.published_at = datetime.now(timezone.utc)
        await session.commit()
        return {"ok": True, "data": {"status": doc.publish_status}}


@router.get("/documents/{document_id}/publish-status")
async def get_publish_status(document_id: uuid.UUID):
    factory = get_session_factory()
    async with factory() as session:
        doc = await session.get(AnswerDocument, document_id)
        if not doc:
            raise HTTPException(status_code=404)
        return {"ok": True, "data": {
            "status": doc.publish_status,
            "publishUrl": doc.publish_url,
            "publishedAt": doc.published_at.isoformat() if doc.published_at else None,
        }}


@router.post("/documents/{document_id}/metrics")
async def add_metrics(document_id: uuid.UUID, req: MetricsRequest):
    factory = get_session_factory()
    async with factory() as session:
        doc = await session.get(AnswerDocument, document_id)
        if not doc:
            raise HTTPException(status_code=404)
        m = PublishMetricsModel(
            document_id=document_id,
            views=req.views,
            likes=req.likes,
            comments=req.comments,
            collects=req.collects,
            label=req.label,
        )
        session.add(m)
        await session.commit()
        return {"ok": True, "data": {"id": str(m.id)}}


@router.get("/documents/{document_id}/metrics")
async def list_metrics(document_id: uuid.UUID):
    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(
            select(PublishMetricsModel)
            .where(PublishMetricsModel.document_id == document_id)
            .order_by(PublishMetricsModel.recorded_at.desc())
        )).scalars().all()
        return {"ok": True, "data": [
            {"id": str(r.id), "views": r.views, "likes": r.likes,
             "comments": r.comments, "collects": r.collects,
             "label": r.label, "recordedAt": r.recorded_at.isoformat()}
            for r in rows
        ]}


@router.delete("/documents/{document_id}/metrics/{metric_id}")
async def delete_metrics(document_id: uuid.UUID, metric_id: uuid.UUID):
    factory = get_session_factory()
    async with factory() as session:
        m = await session.get(PublishMetricsModel, metric_id)
        if not m or m.document_id != document_id:
            raise HTTPException(status_code=404)
        await session.delete(m)
        await session.commit()
        return {"ok": True, "data": {"deleted": True}}
