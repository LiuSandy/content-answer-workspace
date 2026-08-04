"""APScheduler 进程内定时任务基建；Phase 2 主动感知。

启动时注册机会扫描任务，按 AgentSettings.scan_interval_hours 间隔执行。
非活跃时段（凌晨 1-7 点）跳过扫描以节省 API 配额。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def start_scheduler():
    """在 FastAPI startup 中调用；注册时机扫描任务并启动 scheduler。"""
    sched = get_scheduler()
    sched.add_job(
        _scan_opportunities_job,
        IntervalTrigger(hours=1),
        id="opportunity_scanner",
        replace_existing=True,
    )
    if not sched.running:
        sched.start()
    logger.info("APScheduler started; opportunity scanner registered hourly")


async def stop_scheduler():
    """在 FastAPI shutdown 中调用。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")


async def _scan_opportunities_job():
    """定时任务：每小时扫一次热榜并算机会得分。

    凌晨 1-7 点跳过（非活跃时段，spec 第 8 节风险应对）。
    实际扫描逻辑在 OpportunityService.scan_and_persist。
    """
    from datetime import datetime
    now = datetime.now()
    if 1 <= now.hour < 7:
        logger.info("Skip opportunity scan in inactive hours (1-7am)")
        return

    try:
        from ...application.opportunity_service import OpportunityService
        from ...persistence.session import get_session_factory
        factory = get_session_factory()
        async with factory() as session:
            svc = OpportunityService(session)
            count = await svc.scan_and_persist(workspace_id="default")
            logger.info("Opportunity scan completed: %d new opportunities", count)
    except Exception as e:
        logger.error("Opportunity scan job failed: %s", e)