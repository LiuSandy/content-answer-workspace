from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.knowledge.adapters.db.models import (
    KnowledgeIngestionJobModel,
    KnowledgeIngestionPageModel,
)
from app.platform.config.runtime import KnowledgeSettings, get_knowledge_settings
from app.platform.files.pdf_pages import PdfPageWorkspace

logger = logging.getLogger(__name__)

TERMINAL_JOB_STATUSES = ("succeeded", "completed_with_errors", "failed")


async def cleanup_expired_ingestion_jobs(
    session_factory: async_sessionmaker[AsyncSession],
    settings: KnowledgeSettings | None = None,
) -> int:
    """删除超过保留期限的终态入库任务及其页面记录。"""
    settings = settings or get_knowledge_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ingestion_job_retention_days)

    async with session_factory() as session:
        candidates = list(
            (
                await session.execute(
                    select(KnowledgeIngestionJobModel)
                    .where(
                        KnowledgeIngestionJobModel.status.in_(TERMINAL_JOB_STATUSES),
                        KnowledgeIngestionJobModel.completed_at.is_not(None),
                        KnowledgeIngestionJobModel.completed_at < cutoff,
                        KnowledgeIngestionJobModel.lease_owner.is_(None),
                    )
                )
            ).scalars().all()
        )
        if not candidates:
            return 0

        latest_rows = (
            await session.execute(
                select(
                    KnowledgeIngestionJobModel.source_file_id,
                    func.max(KnowledgeIngestionJobModel.created_at),
                ).group_by(KnowledgeIngestionJobModel.source_file_id)
            )
        ).all()
        latest_created_at = {source_id: created_at for source_id, created_at in latest_rows}
        jobs = [
            job
            for job in candidates
            if job.created_at != latest_created_at.get(job.source_file_id)
        ]
        if not jobs:
            return 0

        job_ids = [job.id for job in jobs]
        # 先清理文件，再删除页面和任务记录；页面表也有数据库级 CASCADE，
        # 显式删除可以让该逻辑在不同数据库外键设置下都保持清晰可控。
        for job in jobs:
            PdfPageWorkspace.cleanup_job(settings.ingestion_work_dir, job.id)
        await session.execute(
            delete(KnowledgeIngestionPageModel).where(
                KnowledgeIngestionPageModel.job_id.in_(job_ids)
            )
        )
        await session.execute(
            delete(KnowledgeIngestionJobModel).where(
                KnowledgeIngestionJobModel.id.in_(job_ids)
            )
        )
        await session.commit()
        logger.info("Cleaned up %d expired knowledge ingestion jobs", len(jobs))
        return len(jobs)
