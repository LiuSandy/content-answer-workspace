"""Phase 4 长期记忆 API（R5 完善：status lifecycle + evidence）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.memory.service import (
    list_memories,
    delete_memory,
    clear_all_memories,
    create_memory,
    confirm_memory,
    reject_memory,
    update_memory_content,
)

router = APIRouter(prefix="/api/memories", tags=["memories"])


def _serialize(m):
    return {
        "id": str(m.id),
        "memoryType": m.memory_type,
        "memoryScope": m.memory_scope,
        "content": m.content,
        "confidence": m.confidence,
        "source": m.source,
        "status": m.status,
        "evidence": m.evidence,
        "createdAt": m.created_at.isoformat() if m.created_at else None,
        "activationCount": m.activation_count,
    }


@router.get("")
async def list_user_memories(workspace_id: str = "default"):
    rows = await list_memories(workspace_id)
    return {"ok": True, "data": [_serialize(m) for m in rows]}


class DeleteRequest(BaseModel):
    workspace_id: str = Field("default", alias="workspaceId")


@router.delete("/{memory_id}")
async def delete_user_memory(memory_id: str, workspace_id: str = "default"):
    ok = await delete_memory(memory_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "data": {"deleted": True}}


@router.delete("")
async def clear_all_user_memories(workspace_id: str = "default"):
    count = await clear_all_memories(workspace_id)
    return {"ok": True, "data": {"deletedCount": count}}


# ── R5 记忆生命周期 ──────────────────────────────────────────────────────────────


class CreateMemoryRequest(BaseModel):
    content: str
    memoryType: str = Field("explicit", alias="memoryType")
    memoryScope: str = Field("general", alias="memoryScope")
    confidence: float = 0.8
    evidence: str | None = None
    workspaceId: str = Field("default", alias="workspaceId")

    model_config = {"populate_by_name": True}


@router.post("")
async def create_user_memory(req: CreateMemoryRequest):
    mt = req.memoryType
    if mt not in ("explicit", "implicit", "work_pattern"):
        mt = "explicit"
    mem = await create_memory(
        workspace_id=str(req.workspaceId),
        memory_type=mt,
        memory_scope=req.memoryScope,
        content=str(req.content),
        confidence=req.confidence,
        evidence=req.evidence,
    )
    return {"ok": True, "data": _serialize(mem)}


@router.post("/{memory_id}/confirm")
async def confirm_user_memory(memory_id: str, workspace_id: str = "default"):
    mem = await confirm_memory(memory_id, workspace_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "data": _serialize(mem)}


@router.post("/{memory_id}/reject")
async def reject_user_memory(memory_id: str, workspace_id: str = "default"):
    mem = await reject_memory(memory_id, workspace_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "data": _serialize(mem)}


class UpdateMemoryRequest(BaseModel):
    content: str
    confidence: float | None = None
    workspace_id: str = Field("default", alias="workspaceId")
    model_config = {"populate_by_name": True}


@router.put("/{memory_id}")
async def update_user_memory(memory_id: str, req: UpdateMemoryRequest):
    mem = await update_memory_content(
        memory_id, req.workspace_id, req.content, req.confidence
    )
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "data": _serialize(mem)}
