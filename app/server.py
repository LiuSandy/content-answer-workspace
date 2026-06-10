from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes.config import router as config_router
from .api.routes.session import router as session_router
from .api.routes.workflow import router as workflow_router
from .application.workflow_service import WorkflowService
from .core.config import GENERATED_IMAGES_DIR, load_env_file
from .models import RegeneratePayload, RunPayload, SessionPayload
from .services.session_service import cookie_status, read_latest_session, save_session

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"

app = FastAPI()
workflow_service = WorkflowService()
GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/generated-images", StaticFiles(directory=GENERATED_IMAGES_DIR), name="generated-images")


@app.exception_handler(Exception)
async def handle_exception(_: Request, error: Exception) -> JSONResponse:
    """统一包装后端异常响应；这样前端可以用一致结构展示错误消息。"""

    if isinstance(error, HTTPException):
        return JSONResponse(
            status_code=error.status_code,
            content={"ok": False, "error": {"message": str(error.detail)}},
        )
    return JSONResponse(status_code=500, content={"ok": False, "error": {"message": str(error)}})


@app.get("/api/health")
async def health() -> JSONResponse:
    """返回服务健康状态；这样前端或本地联调可以快速确认后端已启动。"""

    return JSONResponse({"ok": True, "data": {"status": "ok"}})


app.include_router(config_router)
app.include_router(session_router)
app.include_router(workflow_router)


# Legacy compatibility endpoints while the frontend is being migrated.
@app.get("/api/config")
async def legacy_get_config() -> JSONResponse:
    """提供旧版配置接口兼容；这样迁移期间旧前端或脚本仍能读取初始化配置。"""

    response = await config_router.routes[0].endpoint()
    return response


@app.get("/api/session/latest")
async def legacy_get_latest_session() -> JSONResponse:
    """提供旧版最近会话接口兼容；这样历史调用路径不需要立即迁移。"""

    return JSONResponse({"session": read_latest_session()})


@app.get("/api/cookie-status")
async def legacy_cookie_status() -> JSONResponse:
    """提供旧版 cookie 状态接口兼容；这样旧工作台仍能检查知乎凭据文件。"""

    return JSONResponse(cookie_status(os.getenv("ZHIHU_COOKIE_FILE", "").strip()))


@app.post("/api/run")
async def legacy_run(payload: RunPayload) -> JSONResponse:
    """提供旧版采集接口兼容；这样旧调用也能复用新的平台工作流服务。"""

    try:
        result = await workflow_service.collect(payload)
        return JSONResponse(result.model_dump(by_alias=True))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/regenerate")
async def legacy_regenerate(payload: RegeneratePayload) -> JSONResponse:
    """提供旧版单条重新生成接口兼容；这样历史按钮调用仍走统一 DeepSeek 生成逻辑。"""

    try:
        item = await workflow_service.generate_one(payload)
        return JSONResponse({"item": item.model_dump(by_alias=True)})
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/generate-all")
async def legacy_generate_all(payload: SessionPayload) -> JSONResponse:
    """提供旧版批量生成接口兼容；这样旧请求格式可以继续批量生成回答。"""

    try:
        items = await workflow_service.generate_many(payload)
        return JSONResponse({"items": [item.model_dump(by_alias=True) for item in items]})
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/save")
async def legacy_save(payload: SessionPayload) -> JSONResponse:
    """提供旧版保存接口兼容；这样历史前端仍可把当前会话写入本地。"""

    file_path = save_session(payload)
    return JSONResponse({"ok": True, "filePath": file_path})


if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    @app.get("/")
    async def root() -> JSONResponse:
        """返回未构建前端时的提示；这样只启动后端也能得到明确的运行说明。"""

        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "message": "Frontend dist is not built yet. Run the frontend dev server or build frontend/dist first."
                },
            }
        )


def main() -> None:
    """启动本地 FastAPI 服务；这样命令行运行模块时可以加载环境变量并保持启动行为稳定可控。"""

    load_env_file()
    port = int(os.getenv("PORT", "3000"))
    uvicorn.run("app.server:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
