"""Phase 4 长期记忆 API。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...application.memory_service import (
    list_memories, delete_memory, clear_all_memories,
)
from ...persistence.session import get_session_factory
from ...persistence.models.user_memories import UserMemoryModel

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("")
async def list_user_memories(workspace_id: str = "default"):
    rows = await list_memories(workspace_id)
    return {"ok": True, "data": [
        {
            "id": str(m.id),
            "memoryType": m.memory_type,
            "content": m.content,
            "confidence": m.confidence,
            "source": m.source,
            "createdAt": m.created_at.isoformat() if m.created_at else None,
            "activationCount": m.activation_count,
        }
        for m in rows
    ]}


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


class UpdateMemoryRequest(BaseModel):
    content: str
    confidence: float | None = None
    workspace_id: str = Field("default", alias="workspaceId")
    model_config = {"populate_by_name": True}


@router.put("/{memory_id}")
async def update_user_memory(memory_id: str, req: UpdateMemoryRequest):
    factory = get_session_factory()
    async with factory() as session:
        mem = await session.get(UserMemoryModel, uuid.UUID(memory_id))
        if not mem or mem.workspace_id != req.workspace_id:
            raise HTTPException(status_code=404, detail="Memory not found")
        mem.content = req.content
        if req.confidence is not None:
            mem.confidence = req.confidence
        await session.commit()
    return {"ok": True, "data": {"updated": True}}