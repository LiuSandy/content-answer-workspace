"""APScheduler 进程内定时任务基建。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.config.runtime import get_knowledge_settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def start_scheduler(session_factory: async_sessionmaker[AsyncSession] | None = None):
    """在 FastAPI startup 中调用并启动 scheduler。"""
    sched = get_scheduler()
    if session_factory is not None:
        from app.modules.knowledge.application.ingestion_cleanup import cleanup_expired_ingestion_jobs

        settings = get_knowledge_settings()
        sched.add_job(
            cleanup_expired_ingestion_jobs,
            "interval",
            seconds=settings.ingestion_cleanup_interval_seconds,
            args=[session_factory, settings],
            id="knowledge-ingestion-cleanup",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    if not sched.running:
        sched.start()
    logger.info("APScheduler started")


async def stop_scheduler():
    """在 FastAPI shutdown 中调用。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
