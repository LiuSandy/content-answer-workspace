"""FastAPI composition root and executable server entry point."""

from __future__ import annotations

import os
from pathlib import Path

from app.platform.config.runtime import GENERATED_IMAGES_DIR, load_env_file

# 路由模块可能在导入时读取环境配置，因此必须先加载项目根目录的 .env。
load_env_file()

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.bootstrap.lifecycle import lifespan
from app.bootstrap.router import (
    handle_app_exception,
    handle_db_exception,
    handle_exception,
    health,
    register_http,
)
from app.platform.observability.logging import configure_logging
from app.platform.observability.middleware import RequestLoggingMiddleware

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"


def create_app() -> FastAPI:
    """组装应用；业务模块只通过各自公开的 API Router 接入。"""
    application = FastAPI(lifespan=lifespan)
    application.add_middleware(RequestLoggingMiddleware)
    register_http(application)

    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/generated-images",
        StaticFiles(directory=GENERATED_IMAGES_DIR),
        name="generated-images",
    )

    if FRONTEND_DIST_DIR.exists():
        application.mount(
            "/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend"
        )
    else:

        @application.get("/")
        async def root() -> JSONResponse:
            return JSONResponse(
                {
                    "ok": True,
                    "data": {
                        "message": "Frontend dist is not built yet. Run the frontend dev server or build frontend/dist first."
                    },
                }
            )

    return application


app = create_app()


def main() -> None:
    load_env_file()
    configure_logging()
    uvicorn.run(
        "app.bootstrap.server:app",
        host="127.0.0.1",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
