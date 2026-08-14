from __future__ import annotations

import asyncio
import hashlib
import logging
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.services.rag.document_service import DocumentService
from app.config.runtime import KnowledgeSettings, get_knowledge_settings
from app.contracts.knowledge import KnowledgeDocumentStatus, SourceType
from app.infrastructure.files.source_files import SourceFileStorage
from app.infrastructure.files.pdf_pages import PdfPageWorkspace, strip_markdown_front_matter
from app.infrastructure.database.repositories.knowledge_storage import KnowledgeStorage
from app.infrastructure.database.models.knowledge import (
    KnowledgeDocumentModel,
    KnowledgeIngestionJobModel,
    KnowledgeIngestionPageModel,
    KnowledgeSourceFileModel,
)
from app.infrastructure.observability.context import bind_log_context, reset_log_context, set_log_context

logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
_scan_lock = asyncio.Lock()


@dataclass(frozen=True)
class ScanResult:
    discovered: int = 0
    queued: int = 0
    duplicates: int = 0
    failed: int = 0


def source_file_to_dict(source: KnowledgeSourceFileModel, job: KnowledgeIngestionJobModel | None = None) -> dict:
    return {
        "id": str(source.id),
        "workspaceId": source.workspace_id,
        "ownerId": source.owner_id,
        "ingestSource": source.ingest_source,
        "originalFilename": source.original_filename,
        "originalRelativePath": source.original_relative_path,
        "currentRelativePath": source.current_relative_path,
        "extension": source.extension,
        "sizeBytes": source.size_bytes,
        "contentHash": source.content_hash,
        "status": source.status,
        "knowledgeDocumentId": str(source.knowledge_document_id) if source.knowledge_document_id else None,
        "failureCode": source.failure_code,
        "failureReason": source.failure_reason,
        "createdAt": source.created_at.isoformat() if source.created_at else None,
        "updatedAt": source.updated_at.isoformat() if source.updated_at else None,
        "job": ingestion_job_to_dict(job) if job else None,
    }


def ingestion_job_to_dict(job: KnowledgeIngestionJobModel) -> dict:
    return {
        "id": str(job.id),
        "sourceFileId": str(job.source_file_id),
        "attempt": job.attempt,
        "status": job.status,
        "stage": job.stage,
        "progressCurrent": job.progress_current,
        "progressTotal": job.progress_total,
        "progressPercent": job.progress_percent,
        "retryCount": job.retry_count,
        "totalPages": job.total_pages,
        "completedPages": job.completed_pages,
        "succeededPages": job.succeeded_pages,
        "failedPages": job.failed_pages,
        "currentPage": job.current_page,
        "errorCode": job.error_code,
        "errorMessage": job.error_message,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
        "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
    }


class SourceIngestionService:
    def __init__(self, session: AsyncSession, settings: KnowledgeSettings | None = None):
        self.session = session
        self.settings = settings or get_knowledge_settings()
        self.files = SourceFileStorage(self.settings.source_files_dir)

    async def scan_pending(
        self,
        workspace_id: str = "default",
        owner_id: str = "default",
        ingest_source: str = "directory_scan",
    ) -> ScanResult:
        discovered = queued = duplicates = failed = 0
        async with _scan_lock:
            paths = self.files.iter_pending()
            first_stats = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in paths}
            if paths and self.settings.source_file_stable_seconds:
                await asyncio.sleep(self.settings.source_file_stable_seconds)
            for path in paths:
                discovered += 1
                try:
                    current = path.stat()
                except FileNotFoundError:
                    continue
                if first_stats[path] != (current.st_size, current.st_mtime_ns):
                    continue
                outcome, _ = await self._register(path, workspace_id, owner_id, ingest_source)
                queued += outcome == "queued"
                duplicates += outcome == "duplicate"
                failed += outcome == "failed"
        return ScanResult(discovered, queued, duplicates, failed)

    async def register_uploaded(
        self,
        path: Path,
        workspace_id: str = "default",
        owner_id: str = "default",
        content_hash: str | None = None,
    ) -> tuple[str, KnowledgeSourceFileModel]:
        """登记已经原子写完的上传文件；无需再次等待稳定窗口。"""
        async with _scan_lock:
            return await self._register(
                path, workspace_id, owner_id, "frontend_upload", content_hash=content_hash
            )

    async def _register(
        self,
        path: Path,
        workspace_id: str,
        owner_id: str,
        ingest_source: str,
        content_hash: str | None = None,
    ) -> tuple[str, KnowledgeSourceFileModel]:
        pending_relative = self.files.pending_relative(path)
        extension = path.suffix.lower()
        size_bytes = path.stat().st_size
        source = KnowledgeSourceFileModel(
            workspace_id=workspace_id,
            owner_id=owner_id,
            ingest_source=ingest_source,
            original_filename=path.name,
            original_relative_path=str(pending_relative),
            current_relative_path=str(Path("pending") / pending_relative),
            extension=extension.lstrip("."),
            size_bytes=size_bytes,
            content_hash=content_hash,
            status="pending",
        )
        self.session.add(source)
        await self.session.flush()
        job = KnowledgeIngestionJobModel(
            source_file_id=source.id,
            status="running",
            stage="hashing",
            progress_current=0,
            progress_total=max(size_bytes, 1),
            progress_percent=2,
        )
        self.session.add(job)
        await self.session.flush()

        if extension not in SUPPORTED_EXTENSIONS:
            reason = f"暂不支持 {extension or '无扩展名'}，当前支持 PDF、Markdown 和 TXT"
            await self._terminal_failure(source, "unsupported_file_type", reason, "validating", job)
            return "failed", source
        if size_bytes > self.settings.max_source_file_bytes:
            reason = f"文件超过大小上限 {self.settings.max_source_file_bytes // (1024 * 1024)}MB"
            await self._terminal_failure(source, "file_too_large", reason, "validating", job)
            return "failed", source

        if content_hash is None:
            content_hash = await self._stream_hash(path, job)
        source.content_hash = content_hash

        existing = (
            await self.session.execute(
                select(KnowledgeDocumentModel).where(
                    KnowledgeDocumentModel.workspace_id == workspace_id,
                    KnowledgeDocumentModel.source_content_hash == content_hash,
                    KnowledgeDocumentModel.status != KnowledgeDocumentStatus.DELETED.value,
                )
            )
        ).scalars().first()
        if existing:
            source.knowledge_document_id = existing.id
            reason = f"文件内容与已存在资料《{existing.title}》相同"
            await self._terminal_failure(source, "duplicate_source", reason, "deduplicating", job)
            return "duplicate", source

        moved = self.files.move(source.current_relative_path, "processing", source.id)
        source.current_relative_path = str(moved)
        source.status = "processing"
        doc = KnowledgeDocumentModel(
            workspace_id=workspace_id,
            owner_id=owner_id,
            source_type=self._source_type(extension),
            title=path.name,
            source_path=str(self.files.resolve_relative(moved)),
            source_content_hash=content_hash,
            status=KnowledgeDocumentStatus.PENDING.value,
            doc_metadata={"sourceFileId": str(source.id), "sourceRelativePath": str(pending_relative)},
        )
        self.session.add(doc)
        await self.session.flush()
        source.knowledge_document_id = doc.id
        job.status = "queued"
        job.stage = "discovered"
        job.progress_current = 8
        job.progress_total = 100
        job.progress_percent = 8
        await self.session.commit()
        return "queued", source

    async def _stream_hash(self, path: Path, job: KnowledgeIngestionJobModel) -> str:
        digest = hashlib.sha256()
        completed = 0
        last_saved = 0
        with path.open("rb") as handle:
            while chunk := await asyncio.to_thread(
                handle.read, self.settings.source_file_buffer_bytes
            ):
                digest.update(chunk)
                completed += len(chunk)
                if completed - last_saved >= 64 * 1024 * 1024 or completed == job.progress_total:
                    job.progress_current = completed
                    job.progress_percent = 2 + min(6, int(completed / max(job.progress_total, 1) * 6))
                    await self.session.flush()
                    last_saved = completed
        return digest.hexdigest()

    async def _terminal_failure(
        self,
        source: KnowledgeSourceFileModel,
        code: str,
        reason: str,
        stage: str,
        job: KnowledgeIngestionJobModel | None = None,
    ) -> None:
        moved = self.files.move(source.current_relative_path, "failed", source.id)
        source.current_relative_path = str(moved)
        source.status = "failed"
        source.failure_code = code
        source.failure_reason = reason
        if job is None:
            job = KnowledgeIngestionJobModel(
                source_file_id=source.id,
            )
            self.session.add(job)
        job.status = "failed"
        job.stage = stage
        job.progress_current = job.progress_total
        job.progress_percent = 100
        job.error_code = code
        job.error_message = reason
        job.completed_at = datetime.now(timezone.utc)
        await self.session.commit()

    async def list_sources(self, workspace_id: str) -> list[dict]:
        rows = (
            await self.session.execute(
                select(KnowledgeSourceFileModel)
                .where(KnowledgeSourceFileModel.workspace_id == workspace_id)
                .options(selectinload(KnowledgeSourceFileModel.jobs))
                .order_by(KnowledgeSourceFileModel.created_at.desc())
            )
        ).scalars().all()
        result = []
        for source in rows:
            latest = max(source.jobs, key=lambda job: job.created_at or datetime.min.replace(tzinfo=timezone.utc), default=None)
            result.append(source_file_to_dict(source, latest))
        return result

    @staticmethod
    def _source_type(extension: str) -> str:
        if extension in {".md", ".markdown"}:
            return SourceType.MARKDOWN.value
        if extension == ".pdf":
            return SourceType.PDF.value
        return SourceType.TEXT.value


class IngestionExecutor:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: KnowledgeSettings | None = None):
        self.session_factory = session_factory
        self.settings = settings or get_knowledge_settings()
        self.files = SourceFileStorage(self.settings.source_files_dir)
        self.instance_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:10]}"
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._workers: list[asyncio.Task] = []
        self._scan_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self.recover_stale_jobs(force=True)
        await self.reconcile_processing_files()
        self._workers = [
            asyncio.create_task(self._worker_loop(), name=f"knowledge-ingestion-{index}")
            for index in range(self.settings.ingestion_concurrency)
        ]
        self._scan_task = asyncio.create_task(
            self._scan_on_startup(), name="knowledge-ingestion-startup-scan"
        )
        self.wake()

    async def _scan_on_startup(self) -> None:
        try:
            async with self.session_factory() as session:
                await SourceIngestionService(session, self.settings).scan_pending()
            self.wake()
        except Exception:
            logger.exception("Knowledge source startup scan failed")

    async def reconcile_processing_files(self) -> int:
        """将没有数据库记录的 processing 文件退回 pending，修复移动后提交前崩溃。"""
        async with self.session_factory() as session:
            known = set((await session.execute(
                select(KnowledgeSourceFileModel.current_relative_path).where(
                    KnowledgeSourceFileModel.status.in_(["processing", "recognized", "archived"])
                )
            )).scalars().all())
        repaired = 0
        processing = self.files.state_dir("processing")
        for path in processing.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            relative = str(path.relative_to(self.files.root))
            if relative in known:
                continue
            relative_inside = path.relative_to(processing)
            target = self.files.state_dir("pending") / relative_inside
            target = self.files._available_target(target, None)
            target.parent.mkdir(parents=True, exist_ok=True)
            path.replace(target)
            repaired += 1
        return repaired

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._scan_task:
            self._scan_task.cancel()
        if self._workers:
            for worker in self._workers:
                worker.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)
        if self._scan_task:
            await asyncio.gather(self._scan_task, return_exceptions=True)

    def wake(self) -> None:
        self._wake.set()

    async def recover_stale_jobs(self, force: bool = False) -> int:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            job_conditions = [KnowledgeIngestionJobModel.status == "running"]
            page_conditions = [KnowledgeIngestionPageModel.status == "running"]
            if not force:
                job_conditions.append(KnowledgeIngestionJobModel.lease_expires_at < now)
                page_conditions.append(KnowledgeIngestionPageModel.lease_expires_at < now)
            jobs = (
                await session.execute(
                    select(KnowledgeIngestionJobModel).where(*job_conditions)
                )
            ).scalars().all()
            for job in jobs:
                job.status = "queued"
                job.stage = "recovering"
                job.retry_count += 1
                job.lease_owner = None
                job.lease_expires_at = None
            await session.execute(
                update(KnowledgeIngestionPageModel)
                .where(*page_conditions)
                .values(status="pending", lease_owner=None, lease_expires_at=None)
            )
            await session.commit()
            return len(jobs)

    async def _worker_loop(self) -> None:
        while not self._stop.is_set():
            job_id = await self._claim_next()
            if job_id:
                await self._process(job_id)
                continue
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=5)
            except TimeoutError:
                await self.recover_stale_jobs()

    async def _claim_next(self) -> UUID | None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            job = (
                await session.execute(
                    select(KnowledgeIngestionJobModel)
                    .where(KnowledgeIngestionJobModel.status == "queued")
                    .order_by(KnowledgeIngestionJobModel.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not job:
                return None
            job.status = "running"
            job.stage = "preparing"
            job.progress_percent = max(job.progress_percent, 10)
            job.progress_current = job.progress_percent
            job.lease_owner = self.instance_id
            job.heartbeat_at = now
            job.lease_expires_at = now + timedelta(seconds=self.settings.ingestion_lease_seconds)
            job.started_at = job.started_at or now
            await session.commit()
            return job.id

    async def _process(self, job_id: UUID) -> None:
        heartbeat: asyncio.Task | None = None
        log_token = set_log_context(job_id=str(job_id))
        try:
            heartbeat = asyncio.create_task(self._heartbeat(job_id))
            async with self.session_factory() as session:
                job = (
                    await session.execute(
                        select(KnowledgeIngestionJobModel)
                        .where(KnowledgeIngestionJobModel.id == job_id)
                        .options(selectinload(KnowledgeIngestionJobModel.source_file))
                    )
                ).scalar_one()
                source = job.source_file
                doc = await session.get(KnowledgeDocumentModel, source.knowledge_document_id)
                if not doc:
                    raise RuntimeError("Knowledge document missing for ingestion job")
                reset_log_context(log_token)
                log_token = set_log_context(
                    job_id=str(job.id), source_file_id=str(source.id), document_id=str(doc.id)
                )
                path = self._locate_source(source)
                actual_relative = str(path.relative_to(self.files.root))
                if actual_relative != source.current_relative_path:
                    source.current_relative_path = actual_relative
                    source.status = Path(actual_relative).parts[0]
                    doc.source_path = str(path)
                    await session.commit()
                storage = KnowledgeStorage(self.settings.sources_dir, self.settings.documents_dir)
                documents = DocumentService(session, storage)
                extension = f".{source.extension.lower()}"
                if extension in {".md", ".markdown"}:
                    file_bytes = path.read_bytes()
                    await self._progress(session, job, "parsing", 25)
                    markdown = file_bytes.decode("utf-8", errors="replace")
                    await self._progress(session, job, "saving_markdown", 80)
                    published = storage.publish_markdown(doc.id, markdown)
                    doc.markdown_path = str(published)
                    doc.markdown_content_hash = None
                    doc.status = KnowledgeDocumentStatus.INDEXING.value
                    moved = self.files.move(source.current_relative_path, "archived", source.id)
                    source.current_relative_path = str(moved)
                    source.status = "archived"
                    doc.source_path = str(self.files.resolve_relative(moved))
                    await session.commit()
                    await self._progress(session, job, "dispatching_index", 90)
                    # 后续索引保持现有行为，不把索引结果反向改写为源文件识别失败。
                    from app.api.routes.knowledge import _run_indexing_task
                    asyncio.create_task(
                        _run_indexing_task(doc.id, source.workspace_id, source.owner_id),
                        name=f"knowledge-index-{doc.id}",
                    )
                elif extension == ".pdf":
                    completed_with_errors = await self._process_pdf(
                        session, job, source, doc, path, documents
                    )
                    await self._complete(
                        session,
                        job,
                        status="completed_with_errors" if completed_with_errors else "succeeded",
                    )
                    return
                else:
                    file_bytes = path.read_bytes()
                    await self._progress(session, job, "parsing", 25)
                    try:
                        markdown = file_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        markdown = file_bytes.decode("gbk", errors="replace")
                    confidence = 1.0
                    await self._progress(session, job, "saving_candidate", 90)
                    await documents.save_candidate_markdown(doc.id, markdown, source.workspace_id, confidence)
                    doc.status = KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value
                    moved = self.files.move(source.current_relative_path, "recognized", source.id)
                    source.current_relative_path = str(moved)
                    source.status = "recognized"
                    doc.source_path = str(self.files.resolve_relative(moved))
                    await session.commit()

                await self._complete(session, job)
        except Exception as exc:
            logger.exception("Knowledge ingestion failed for job %s", job_id)
            await self._fail(job_id, exc)
        finally:
            if heartbeat:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            reset_log_context(log_token)

    def _locate_source(self, source: KnowledgeSourceFileModel) -> Path:
        configured = self.files.resolve_relative(source.current_relative_path)
        if configured.exists():
            return configured
        relative = Path(source.original_relative_path)
        for state in ("processing", "recognized", "archived", "failed"):
            candidate = self.files.state_dir(state) / relative
            if candidate.exists() and candidate.is_file() and not candidate.is_symlink():
                return candidate
            matches = list(candidate.parent.glob(f"{candidate.stem}--{str(source.id)[:8]}*{candidate.suffix}"))
            if matches:
                return matches[0]
        raise FileNotFoundError(source.current_relative_path)

    async def _heartbeat(self, job_id: UUID) -> None:
        interval = max(5, self.settings.ingestion_lease_seconds // 3)
        while True:
            await asyncio.sleep(interval)
            now = datetime.now(timezone.utc)
            async with self.session_factory() as session:
                await session.execute(
                    update(KnowledgeIngestionJobModel)
                    .where(
                        KnowledgeIngestionJobModel.id == job_id,
                        KnowledgeIngestionJobModel.status == "running",
                        KnowledgeIngestionJobModel.lease_owner == self.instance_id,
                    )
                    .values(
                        heartbeat_at=now,
                        lease_expires_at=now + timedelta(seconds=self.settings.ingestion_lease_seconds),
                    )
                )
                await session.commit()

    async def _process_pdf(
        self,
        session: AsyncSession,
        job: KnowledgeIngestionJobModel,
        source: KnowledgeSourceFileModel,
        doc: KnowledgeDocumentModel,
        source_path: Path,
        documents: DocumentService,
    ) -> bool:
        current_hash = await asyncio.to_thread(
            SourceFileStorage.stream_sha256,
            source_path,
            self.settings.source_file_buffer_bytes,
        )
        if current_hash != source.content_hash:
            raise RuntimeError("source_changed")

        workspace = PdfPageWorkspace(self.settings.ingestion_work_dir, job.id)
        total_pages = await asyncio.to_thread(workspace.page_count, source_path)
        if total_pages <= 0:
            raise RuntimeError("PDF 中没有可处理页面")
        job.total_pages = total_pages
        job.stage = "initializing_pages"
        job.progress_current = 0
        job.progress_total = total_pages
        job.progress_percent = 10

        existing_numbers = set((await session.execute(
            select(KnowledgeIngestionPageModel.page_number).where(
                KnowledgeIngestionPageModel.job_id == job.id
            )
        )).scalars().all())
        for page_number in range(1, total_pages + 1):
            if page_number not in existing_numbers:
                session.add(KnowledgeIngestionPageModel(
                    job_id=job.id,
                    page_number=page_number,
                    status="pending",
                ))
        await session.commit()
        succeeded_rows = list((await session.execute(
            select(KnowledgeIngestionPageModel).where(
                KnowledgeIngestionPageModel.job_id == job.id,
                KnowledgeIngestionPageModel.status == "succeeded",
            )
        )).scalars().all())
        for page in succeeded_rows:
            page_path = Path(page.markdown_path) if page.markdown_path else None
            if not page_path or not page_path.exists():
                page.status = "pending"
                page.markdown_path = None
                page.content_hash = None
                page.completed_at = None
                continue
            actual_hash = await asyncio.to_thread(
                SourceFileStorage.stream_sha256,
                page_path,
                self.settings.source_file_buffer_bytes,
            )
            if actual_hash != page.content_hash:
                page.status = "pending"
                page.markdown_path = None
                page.content_hash = None
                page.completed_at = None
        await session.commit()
        await self._refresh_page_summary(session, job)

        while True:
            page_ids = list((
                await session.execute(
                    select(KnowledgeIngestionPageModel.id)
                    .where(
                        KnowledgeIngestionPageModel.job_id == job.id,
                        KnowledgeIngestionPageModel.status == "pending",
                    )
                    .order_by(KnowledgeIngestionPageModel.page_number)
                    .limit(self.settings.pdf_page_concurrency)
                )
            ).scalars().all())
            if not page_ids:
                break
            await asyncio.gather(*[
                self._process_pdf_page_isolated(page_id, source_path)
                for page_id in page_ids
            ])
            await session.refresh(job)

        await self._refresh_page_summary(session, job)
        if job.succeeded_pages == 0:
            raise RuntimeError("所有 PDF 页面均识别失败")

        failed_numbers = set((await session.execute(
            select(KnowledgeIngestionPageModel.page_number).where(
                KnowledgeIngestionPageModel.job_id == job.id,
                KnowledgeIngestionPageModel.status == "failed",
            )
        )).scalars().all())
        job.stage = "merging_markdown"
        job.progress_percent = 94
        await session.commit()
        merged = workspace.merge_pages(total_pages, failed_numbers)
        front_matter = (
            "---\n"
            f"doc_id: {doc.id}\n"
            "source_type: pdf\n"
            f"total_pages: {total_pages}\n"
            f"succeeded_pages: {job.succeeded_pages}\n"
            f"failed_pages: {sorted(failed_numbers)}\n"
            "converter: page_ingestion\n"
            "---\n\n"
        )
        confidences = list((await session.execute(
            select(KnowledgeIngestionPageModel.confidence).where(
                KnowledgeIngestionPageModel.job_id == job.id,
                KnowledgeIngestionPageModel.status == "succeeded",
                KnowledgeIngestionPageModel.confidence.is_not(None),
            )
        )).scalars().all())
        confidence = sum(confidences) / len(confidences) if confidences else None
        job.stage = "saving_candidate"
        job.progress_percent = 98
        await session.commit()
        await documents.save_candidate_markdown(
            doc.id, front_matter + merged, source.workspace_id, confidence
        )
        doc.status = KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value
        if source.status != "recognized":
            moved = self.files.move(source.current_relative_path, "recognized", source.id)
            source.current_relative_path = str(moved)
            source.status = "recognized"
            doc.source_path = str(self.files.resolve_relative(moved))
        await session.commit()
        return bool(failed_numbers)

    async def _process_pdf_page_isolated(self, page_id: UUID, source_path: Path) -> None:
        async with self.session_factory() as session:
            page = await session.get(KnowledgeIngestionPageModel, page_id)
            if not page or page.status != "pending":
                return
            job = await session.get(KnowledgeIngestionJobModel, page.job_id)
            if not job:
                return
            source = await session.get(KnowledgeSourceFileModel, job.source_file_id)
            if not source or not source.knowledge_document_id:
                return
            doc = await session.get(KnowledgeDocumentModel, source.knowledge_document_id)
            if not doc:
                return
            workspace = PdfPageWorkspace(self.settings.ingestion_work_dir, job.id)
            with bind_log_context(
                job_id=str(job.id), source_file_id=str(source.id),
                document_id=str(doc.id), page_number=page.page_number,
            ):
                await self._process_pdf_page(
                    session, job, page, source, doc, source_path, workspace
                )

    async def _process_pdf_page(
        self,
        session: AsyncSession,
        job: KnowledgeIngestionJobModel,
        page: KnowledgeIngestionPageModel,
        source: KnowledgeSourceFileModel,
        doc: KnowledgeDocumentModel,
        source_path: Path,
        workspace: PdfPageWorkspace,
    ) -> None:
        page.status = "running"
        page.attempt_count += 1
        page.lease_owner = self.instance_id
        page.lease_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.ingestion_lease_seconds
        )
        page.started_at = page.started_at or datetime.now(timezone.utc)
        job.stage = "parsing_pages"
        job.current_page = page.page_number
        await session.commit()

        try:
            temporary_pdf = await asyncio.to_thread(
                workspace.extract_single_page, source_path, page.page_number
            )
            page_bytes = temporary_pdf.read_bytes()
            from app.api.routes.knowledge import _parse_pdf_to_markdown

            parsed = await _parse_pdf_to_markdown(
                page_bytes,
                f"{source.original_filename}.page-{page.page_number}.pdf",
                str(doc.id),
                self.settings,
            )
            body = strip_markdown_front_matter(parsed.markdown)
            if not body.strip():
                raise RuntimeError("页面识别结果为空")
            page_path, content_hash = workspace.save_page_markdown(
                page.page_number, body
            )
            page.status = "succeeded"
            page.markdown_path = str(page_path)
            page.content_hash = content_hash
            page.confidence = parsed.confidence
            page.error_code = None
            page.error_message = None
            page.completed_at = datetime.now(timezone.utc)
        except Exception:
            logger.exception("PDF page conversion failed: job=%s page=%s", job.id, page.page_number)
            if page.attempt_count < self.settings.pdf_page_max_attempts:
                page.status = "pending"
                page.error_code = "page_retry"
                page.error_message = "页面识别失败，等待自动重试"
            else:
                page.status = "failed"
                page.error_code = "page_recognition_failed"
                page.error_message = "该页多次识别失败，请在确认前人工补充"
                page.completed_at = datetime.now(timezone.utc)
        finally:
            workspace.remove_temporary_page(page.page_number)
            page.lease_owner = None
            page.lease_expires_at = None
            await session.commit()
            await self._refresh_page_summary(session, job)
            if page.status == "pending":
                await asyncio.sleep(min(2 ** page.attempt_count, 10))

    async def _refresh_page_summary(
        self, session: AsyncSession, job: KnowledgeIngestionJobModel
    ) -> None:
        rows = (await session.execute(
            select(KnowledgeIngestionPageModel.status, func.count())
            .where(KnowledgeIngestionPageModel.job_id == job.id)
            .group_by(KnowledgeIngestionPageModel.status)
        )).all()
        counts = {status: count for status, count in rows}
        job.succeeded_pages = counts.get("succeeded", 0)
        job.failed_pages = counts.get("failed", 0)
        job.completed_pages = job.succeeded_pages + job.failed_pages
        job.progress_current = job.completed_pages
        job.progress_total = max(job.total_pages, 1)
        job.progress_percent = 10 + int(job.completed_pages / max(job.total_pages, 1) * 80)
        await session.commit()

    async def _progress(self, session: AsyncSession, job: KnowledgeIngestionJobModel, stage: str, percent: int) -> None:
        now = datetime.now(timezone.utc)
        job.stage = stage
        job.progress_percent = percent
        job.progress_current = percent
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self.settings.ingestion_lease_seconds)
        await session.commit()

    async def _complete(
        self,
        session: AsyncSession,
        job: KnowledgeIngestionJobModel,
        status: str = "succeeded",
    ) -> None:
        job.status = status
        job.stage = "completed"
        job.progress_current = 100
        job.progress_total = 100
        job.progress_percent = 100
        job.completed_at = datetime.now(timezone.utc)
        job.lease_owner = None
        job.lease_expires_at = None
        await session.commit()

    async def _fail(self, job_id: UUID, exc: Exception) -> None:
        async with self.session_factory() as session:
            job = (
                await session.execute(
                    select(KnowledgeIngestionJobModel)
                    .where(KnowledgeIngestionJobModel.id == job_id)
                    .options(selectinload(KnowledgeIngestionJobModel.source_file))
                )
            ).scalar_one_or_none()
            if not job:
                return
            source = job.source_file
            try:
                moved = self.files.move(source.current_relative_path, "failed", source.id)
                source.current_relative_path = str(moved)
            except FileNotFoundError:
                pass
            source.status = "failed"
            source_changed = str(exc) == "source_changed"
            source.failure_code = "source_changed" if source_changed else "recognition_failed"
            safe_message = (
                "处理期间源 PDF 内容发生变化，任务已停止"
                if source_changed
                else "源文件识别失败，请查看后端日志后重试"
            )
            source.failure_reason = safe_message
            if source.knowledge_document_id:
                doc = await session.get(KnowledgeDocumentModel, source.knowledge_document_id)
                if doc:
                    doc.status = KnowledgeDocumentStatus.FAILED.value
                    doc.conversion_error = safe_message
            job.status = "failed"
            job.stage = "failed"
            job.error_code = source.failure_code
            job.error_message = safe_message
            job.completed_at = datetime.now(timezone.utc)
            job.lease_owner = None
            job.lease_expires_at = None
            await session.commit()


_runtime: IngestionExecutor | None = None


async def start_ingestion_runtime(session_factory: async_sessionmaker[AsyncSession]) -> IngestionExecutor:
    global _runtime
    _runtime = IngestionExecutor(session_factory)
    await _runtime.start()
    return _runtime


async def stop_ingestion_runtime() -> None:
    global _runtime
    if _runtime:
        await _runtime.stop()
        _runtime = None


def wake_ingestion_runtime() -> None:
    if _runtime:
        _runtime.wake()
