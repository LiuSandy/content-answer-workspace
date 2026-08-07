"""FastAPI 入口、路由挂载、静态文件托管和全局生命周期管理。"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path


import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .api.routes.chats import router as chats_router
from .api.routes.documents import router as documents_router
from .api.routes.config import router as config_router
from .api.routes.hotlist import router as hotlist_router
from .api.routes.settings import router as settings_router
from .api.routes.prompts import router as prompts_router
from .api.routes.knowledge import router as knowledge_router
from .api.routes.opportunities import router as opportunities_router
from .api.routes.task_plans import router as task_plans_router
from .api.routes.memories import router as memories_router
from .api.routes.multi_agent import router as multi_agent_router
from .application.agent.graphs.conversation import build_conversation_graph
from .config.loader import warmup as warmup_config
from .core.config import GENERATED_IMAGES_DIR, OUTPUT_DIR, load_env_file
from sqlalchemy.exc import DBAPIError
from .errors import AppError, DocumentConflictError
from .prompts.registry import warmup as warmup_prompts

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
CONVERSATION_CHECKPOINT_DB = OUTPUT_DIR / "agent_checkpoints.sqlite"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化配置与提示词，开启对话历史的 SQLite 连接并编译对话 Graph。"""
    load_env_file()
    warmup_config()
    
    # 自动无感平滑迁移检测与自愈快照护航
    try:
        from scripts.auto_migrate_db import auto_migrate_if_needed
        from app.core.db_guard import create_db_snapshot
        auto_migrate_if_needed()
        create_db_snapshot()
    except Exception as e:
        logging.warning(f"Auto-migration or snapshot guard warning: {e}")

    # 尝试连通性测试
    try:
        from .persistence.session import get_engine
        from sqlalchemy import text
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        logging.info("Database connection established successfully.")
    except Exception as e:
        logging.warning(f"Database pre-flight check warning (PostgreSQL container might be offline): {e}")

    # 初始化 Prompt Registry，直接指向项目根目录下的 prompts 目录
    prompts_dir = ROOT_DIR / "prompts"
    warmup_prompts(prompts_dir, freeze=True)

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    serde = JsonPlusSerializer(allowed_msgpack_modules=[
        ("app.domain.dto", "CollectionRequest"),
        ("app.domain.dto", "ChatResponsePayload"),
        ("app.domain.dto", "AgentError"),
        ("app.domain.dto", "ToolResult"),
        ("app.domain.dto", "SourceItemDTO"),
        "app.domain.dto",
        ("app.application.knowledge.retrieval_service", "RetrievalResult"),
        ("app.application.knowledge.retrieval_service", "RetrievalRequest"),
        ("app.application.agent.state", "ChatAgentState"),
        "asyncpg.pgproto.pgproto",
    ])
    CONVERSATION_CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(CONVERSATION_CHECKPOINT_DB)) as checkpointer:
        checkpointer.serde = serde
        app.state.conversation_graph = build_conversation_graph(checkpointer)
        # Agent 运行期依赖：每 chat 并发锁 + 可注入的 session 工厂（测试可替换）
        from .application.agent.scheduling import ChatRuntime
        from .persistence.session import get_session_factory
        app.state.chat_runtime = ChatRuntime()
        app.state.session_factory = get_session_factory()

        # 启动定时任务基建（Phase 2 主动感知）
        try:
            from .infrastructure.scheduler import start_scheduler
            await start_scheduler()
        except Exception as e:
            logging.warning(f"Scheduler startup warning (non-critical): {e}")

        yield

        # 关闭定时任务
        try:
            from .infrastructure.scheduler import stop_scheduler
            await stop_scheduler()
        except Exception:
            pass


app = FastAPI(lifespan=lifespan)
GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/generated-images", StaticFiles(directory=GENERATED_IMAGES_DIR), name="generated-images")


# ── 异常处理器 ────────────────────────────────────────────────────────────────

@app.exception_handler(DBAPIError)
async def handle_db_exception(_: Request, error: DBAPIError) -> JSONResponse:
    """数据库连接或 SQL 执行异常统一拦截。"""
    logging.error(f"Database error encountered: {error}")
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


@app.exception_handler(AppError)
async def handle_app_exception(_: Request, error: AppError) -> JSONResponse:
    """业务异常统一返回格式。"""
    status_code = 400
    if isinstance(error, DocumentConflictError):
        status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "ok": False,
                "error": {
                    "code": error.error_code,
                    "message": str(error),
                    "expected": error.expected,
                    "actual": error.actual,
                }
            }
        )
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {
                "code": error.error_code,
                "message": str(error),
            }
        }
    )


@app.exception_handler(Exception)
async def handle_exception(_: Request, error: Exception) -> JSONResponse:
    """系统/未知异常统一返回格式。"""
    if isinstance(error, HTTPException):
        return JSONResponse(
            status_code=error.status_code,
            content={"ok": False, "error": {"code": "http_error", "message": str(error.detail)}},
        )
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": {"code": "internal_error", "message": str(error)}},
    )


# ── 路由挂载 ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> JSONResponse:
    """健康检查端点。"""
    return JSONResponse({"ok": True, "data": {"status": "ok"}})


app.include_router(chats_router)
app.include_router(documents_router)
app.include_router(config_router)
app.include_router(hotlist_router)
app.include_router(settings_router)
app.include_router(prompts_router)
app.include_router(knowledge_router)
app.include_router(opportunities_router)
app.include_router(task_plans_router)
app.include_router(memories_router)
app.include_router(multi_agent_router)


# ── 静态文件托管 ──────────────────────────────────────────────────────────────

if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "message": "Frontend dist is not built yet. Run the frontend dev server or build frontend/dist first."
                },
            }
        )


def main() -> None:
    load_env_file()
    port = int(os.getenv("PORT", "3000"))
    uvicorn.run("app.server:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
