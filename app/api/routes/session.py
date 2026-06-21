from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ...models import SessionPayload
from ...services.session_service import (
    cookie_status,
    create_session,
    list_sessions,
    read_latest_session,
    read_session,
    save_session,
)

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("/latest")
async def get_latest_session() -> JSONResponse:
    """返回最近创建的会话；这样前端刷新后可以恢复上一次编辑状态。"""

    return JSONResponse({"ok": True, "data": {"session": read_latest_session()}})


@router.post("/new")
async def new_session() -> JSONResponse:
    """创建一个新的空会话；这样对话页面点「新建对话」时能立刻拿到一个可用的 sessionId。"""

    return JSONResponse({"ok": True, "data": create_session()})


@router.get("/list")
async def get_session_list() -> JSONResponse:
    """列出所有会话摘要；这样对话页面和工作区页面能渲染可切换的会话列表。"""

    return JSONResponse({"ok": True, "data": list_sessions()})


@router.post("/save")
async def save(payload: SessionPayload) -> JSONResponse:
    """保存当前前端会话；这样采集结果和人工编辑回答可以持久化到本地文件。"""

    file_path = save_session(payload)
    return JSONResponse({"ok": True, "data": {"filePath": file_path}})


@router.get("/cookie-status")
async def get_cookie_status() -> JSONResponse:
    """返回知乎 cookie 文件状态；这样前端可以提示采集能力是否具备必要凭据。"""

    return JSONResponse(
        {
            "ok": True,
            "data": cookie_status(os.getenv("ZHIHU_COOKIE_FILE", "").strip()),
        }
    )


@router.get("/{session_id}")
async def get_session_by_id(session_id: str) -> JSONResponse:
    """按 ID 读取指定会话的工作区数据；这样前端切换会话后能恢复对应的采集结果。"""

    session = read_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return JSONResponse({"ok": True, "data": {"session": session}})
