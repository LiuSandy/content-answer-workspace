"""APScheduler 进程内定时任务基建。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def start_scheduler():
    """在 FastAPI startup 中调用并启动 scheduler。"""
    sched = get_scheduler()
    if not sched.running:
        sched.start()
    logger.info("APScheduler started")


async def stop_scheduler():
    """在 FastAPI shutdown 中调用。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
