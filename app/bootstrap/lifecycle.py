"""应用生命周期：启动和关闭所有进程级基础设施。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.modules.conversation.agent.graph import build_chat_agent_graph
from app.modules.writing.agent.graph import writer_graph
from app.platform.config.loader import warmup as warmup_config
from app.platform.config.runtime import OUTPUT_DIR, load_env_file
from app.platform.observability.logging import configure_logging, shutdown_logging
from app.platform.prompts.registry import warmup as warmup_prompts

CONVERSATION_CHECKPOINT_DB = OUTPUT_DIR / "agent_checkpoints.sqlite"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化配置、数据库、Graph、知识摄取与调度器，并在退出时释放资源。"""
    load_env_file()
    configure_logging()
    warmup_config()

    try:
        from scripts.auto_migrate_db import auto_migrate_if_needed
        from app.platform.database.guard import create_db_snapshot

        auto_migrate_if_needed()
        create_db_snapshot()
    except Exception as error:
        logging.warning("Auto-migration or snapshot guard warning: %s", error)

    try:
        from sqlalchemy import text
        from app.platform.database.session import get_engine

        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
        logging.info("Database connection established successfully.")
    except Exception as error:
        logging.warning(
            "Database pre-flight check warning (PostgreSQL container might be offline): %s",
            error,
        )

    warmup_prompts(freeze=True)

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("app.shared.dto", "CollectionRequest"),
            ("app.shared.dto", "ChatResponsePayload"),
            ("app.shared.dto", "AgentError"),
            ("app.shared.dto", "ToolResult"),
            ("app.shared.dto", "SourceItemDTO"),
            "app.shared.dto",
            ("app.modules.knowledge.application.retrieval_service", "RetrievalResult"),
            ("app.modules.knowledge.application.retrieval_service", "RetrievalRequest"),
            ("app.modules.conversation.agent.state", "ChatAgentState"),
            "asyncpg.pgproto.pgproto",
        ]
    )
    CONVERSATION_CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(
        str(CONVERSATION_CHECKPOINT_DB)
    ) as checkpointer:
        checkpointer.serde = serde
        app.state.writer_graph = writer_graph
        app.state.conversation_graph = build_chat_agent_graph(
            checkpointer,
            writer_graph=app.state.writer_graph,
        )

        from app.platform.database.session import get_session_factory
        from app.shared.agent.runtime import ChatRuntime

        app.state.chat_runtime = ChatRuntime()
        app.state.session_factory = get_session_factory()

        try:
            from app.modules.knowledge.application.ingestion_service import start_ingestion_runtime

            app.state.ingestion_runtime = await start_ingestion_runtime(app.state.session_factory)
        except Exception as error:
            logging.warning("Knowledge ingestion startup warning (non-critical): %s", error)

        try:
            from app.platform.scheduler import start_scheduler

            await start_scheduler()
        except Exception as error:
            logging.warning("Scheduler startup warning (non-critical): %s", error)

        yield

        try:
            from app.modules.knowledge.application.ingestion_service import stop_ingestion_runtime

            await stop_ingestion_runtime()
        except Exception:
            pass

        try:
            from app.platform.scheduler import stop_scheduler

            await stop_scheduler()
        except Exception:
            pass

        try:
            from app.platform.database.session import get_engine, reset_engine

            engine = get_engine()
            await engine.dispose()
            reset_engine()
        except Exception:
            pass
        shutdown_logging()


__all__ = ["lifespan"]
