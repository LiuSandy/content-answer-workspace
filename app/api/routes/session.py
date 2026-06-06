from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...models import SessionPayload
from ...services.session_service import cookie_status, read_latest_session, save_session

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("/latest")
async def get_latest_session() -> JSONResponse:
    return JSONResponse({"ok": True, "data": {"session": read_latest_session()}})


@router.post("/save")
async def save(payload: SessionPayload) -> JSONResponse:
    file_path = save_session(payload)
    return JSONResponse({"ok": True, "data": {"filePath": file_path}})


@router.get("/cookie-status")
async def get_cookie_status() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "data": cookie_status(os.getenv("ZHIHU_COOKIE_FILE", "").strip()),
        }
    )
