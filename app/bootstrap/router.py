"""HTTP 路由与全局异常处理器的组合入口。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.modules.acquisition.api.router import router as opportunities_router
from app.modules.conversation.api.router import router as chats_router
from app.modules.documents.api.router import router as documents_router
from app.modules.knowledge.api.router import router as knowledge_router
from app.modules.memory.api.router import router as memories_router
from app.modules.publishing.api.router import router as publishing_router
from app.modules.settings.api.config import router as config_router
from app.modules.settings.api.prompts import router as prompts_router
from app.modules.settings.api.settings import router as settings_router
from app.modules.writing.api.multi_agent import router as multi_agent_router
from app.modules.writing.api.task_plans import router as task_plans_router
from app.shared.errors import AppError, DocumentConflictError


async def handle_db_exception(_: Request, error: DBAPIError) -> JSONResponse:
    logging.error("Database error encountered: %s", error)
    return JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "error": {
                "code": "database_error",
                "message": "Database connection or execution failed. Please ensure PostgreSQL and Alembic migrations are running.",
            },
        },
    )


async def handle_app_exception(_: Request, error: AppError) -> JSONResponse:
    if isinstance(error, DocumentConflictError):
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "error": {
                    "code": error.error_code,
                    "message": str(error),
                    "expected": error.expected,
                    "actual": error.actual,
                },
            },
        )
    return JSONResponse(
        status_code=400,
        content={
            "ok": False,
            "error": {"code": error.error_code, "message": str(error)},
        },
    )


async def handle_exception(_: Request, error: Exception) -> JSONResponse:
    if isinstance(error, HTTPException):
        return JSONResponse(
            status_code=error.status_code,
            content={
                "ok": False,
                "error": {"code": "http_error", "message": str(error.detail)},
            },
        )
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": {"code": "internal_error", "message": str(error)},
        },
    )


async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "data": {"status": "ok"}})


def register_http(app: FastAPI) -> None:
    """注册公共端点、业务路由和统一错误信封。"""
    app.add_exception_handler(DBAPIError, handle_db_exception)
    app.add_exception_handler(AppError, handle_app_exception)
    app.add_exception_handler(Exception, handle_exception)
    app.add_api_route("/api/health", health, methods=["GET"])

    for router in (
        chats_router,
        documents_router,
        config_router,
        settings_router,
        prompts_router,
        knowledge_router,
        opportunities_router,
        task_plans_router,
        memories_router,
        multi_agent_router,
        publishing_router,
    ):
        app.include_router(router)


__all__ = [
    "handle_app_exception",
    "handle_db_exception",
    "handle_exception",
    "health",
    "register_http",
]
