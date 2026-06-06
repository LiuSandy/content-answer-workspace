from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...models import SessionPayload
from ...services.session_service import cookie_status, read_latest_session, save_session

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("/latest")
async def get_latest_session() -> JSONResponse:
    """返回最近保存的会话；这样前端刷新后可以恢复上一次编辑状态。"""

    return JSONResponse({"ok": True, "data": {"session": read_latest_session()}})


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
