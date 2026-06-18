from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ...core.config import load_env_file
from ...services.hotlist_service import fetch_hotlist

router = APIRouter(prefix="/api/hotlist", tags=["hotlist"])


@router.get("")
async def get_hotlist(limit: int = 30) -> JSONResponse:
    """返回知乎当前热榜；这样前端热榜页面可以直接拉取热点数据，不走主题采集工作流。"""
    load_env_file()
    try:
        response = await fetch_hotlist(limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status == 401:
            raise HTTPException(status_code=401, detail="知乎官方 API 鉴权失败，请检查 ZHIHU_ACCESS_SECRET 是否正确配置") from error
        raise HTTPException(status_code=502, detail=f"知乎官方 API 返回错误：{status}") from error
    except httpx.RequestError as error:
        raise HTTPException(status_code=502, detail=f"请求知乎官方 API 失败：{error}") from error
    return JSONResponse({"ok": True, "data": response.model_dump(by_alias=True)})
