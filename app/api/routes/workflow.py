from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ...application.workflow_service import WorkflowService
from ...models import RegeneratePayload, RunPayload, SessionPayload

router = APIRouter(prefix="/api/workflow", tags=["workflow"])
workflow_service = WorkflowService()


@router.post("/collect")
async def collect(payload: RunPayload) -> JSONResponse:
    """接收前端采集请求；这样路由只负责 HTTP 封装，具体平台采集交给工作流服务。"""

    try:
        result = await workflow_service.collect(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return JSONResponse({"ok": True, "data": result.model_dump(by_alias=True)})


@router.post("/generate-one")
async def generate_one(payload: RegeneratePayload) -> JSONResponse:
    """接收单条回答生成请求；这样前端选中的问题可以被直接交给统一生成用例处理。"""

    try:
        answer = await workflow_service.generate_one(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return JSONResponse({"ok": True, "data": {"answer": answer}})


@router.post("/generate")
async def generate(payload: SessionPayload) -> JSONResponse:
    """接收批量回答生成请求；这样前端已有问题列表可以跳过采集直接进入创作流程。"""

    try:
        items = await workflow_service.generate_many(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return JSONResponse({"ok": True, "data": {"items": [item.model_dump(by_alias=True) for item in items]}})
