from __future__ import annotations

import os
import uuid
from dataclasses import replace

import fitz
import pytest
from sqlalchemy import delete, select

from app.services.rag.ingestion_service import IngestionExecutor, SourceIngestionService
from app.config.runtime import get_knowledge_settings
from app.infrastructure.files.parsers import ParsedMarkdown
from app.infrastructure.files.source_files import SourceFileStorage
from app.infrastructure.database.models.knowledge import (
    KnowledgeDocumentModel,
    KnowledgeIngestionJobModel,
    KnowledgeIngestionPageModel,
    KnowledgeSourceFileModel,
)
from app.infrastructure.database.session import get_session_factory


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LARGE_PDF_DB_TESTS") != "1",
    reason="requires migrated local PostgreSQL",
)


def _pdf_bytes(page_count: int) -> bytes:
    document = fitz.open()
    for page_number in range(1, page_count + 1):
        page = document.new_page()
        page.insert_text((50, 50), f"page-{page_number}")
    content = document.tobytes()
    document.close()
    return content


def _settings(tmp_path, **overrides):
    return replace(
        get_knowledge_settings(),
        source_files_dir=tmp_path / "source-files",
        ingestion_work_dir=tmp_path / "ingestion-work",
        sources_dir=tmp_path / "sources",
        documents_dir=tmp_path / "documents",
        source_file_stable_seconds=0,
        mineru_api_key="",
        **overrides,
    )


async def _cleanup(factory, source_id, document_id):
    async with factory() as session:
        if source_id:
            await session.execute(
                delete(KnowledgeSourceFileModel).where(KnowledgeSourceFileModel.id == source_id)
            )
        if document_id:
            await session.execute(
                delete(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id == document_id)
            )
        await session.commit()


@pytest.mark.asyncio
async def test_page_ingestion_persists_pages_and_skips_successes_after_resume(tmp_path, monkeypatch):
    workspace_id = f"large-pdf-{uuid.uuid4().hex}"
    settings = _settings(tmp_path, pdf_page_max_attempts=1)
    storage = SourceFileStorage(settings.source_files_dir)
    pending = storage.state_dir("pending") / "resume.pdf"
    pending.write_bytes(_pdf_bytes(5))
    calls: list[str] = []

    async def fake_parse(page_bytes, filename, doc_id, parser_settings):
        with fitz.open(stream=page_bytes, filetype="pdf") as page_document:
            assert len(page_document) == 1
        calls.append(filename)
        return ParsedMarkdown(
            markdown=f"---\ndoc_id: {doc_id}\n---\n\n{filename}", confidence=0.9
        )

    monkeypatch.setattr("app.api.routes.knowledge._parse_pdf_to_markdown", fake_parse)
    factory = get_session_factory()
    source_id = document_id = None
    try:
        async with factory() as session:
            _, source = await SourceIngestionService(session, settings).register_uploaded(
                pending, workspace_id, "default"
            )
            source_id = source.id
            document_id = source.knowledge_document_id
            job = (
                await session.execute(
                    select(KnowledgeIngestionJobModel).where(
                        KnowledgeIngestionJobModel.source_file_id == source.id
                    )
                )
            ).scalar_one()
            job_id = job.id

        executor = IngestionExecutor(factory, settings)
        await executor._process(job_id)

        async with factory() as session:
            job = await session.get(KnowledgeIngestionJobModel, job_id)
            source = await session.get(KnowledgeSourceFileModel, source_id)
            document = await session.get(KnowledgeDocumentModel, document_id)
            pages = list(
                (
                    await session.execute(
                        select(KnowledgeIngestionPageModel)
                        .where(KnowledgeIngestionPageModel.job_id == job_id)
                        .order_by(KnowledgeIngestionPageModel.page_number)
                    )
                ).scalars().all()
            )
            assert job.status == "succeeded"
            assert (job.total_pages, job.completed_pages, job.succeeded_pages, job.failed_pages) == (
                5, 5, 5, 0
            )
            assert source.status == "recognized"
            assert document.status == "awaiting_confirmation"
            assert [page.status for page in pages] == ["succeeded"] * 5
            assert len(calls) == 5
            job.status = "queued"
            await session.commit()

        await executor._process(job_id)
        assert len(calls) == 5
    finally:
        await _cleanup(factory, source_id, document_id)


@pytest.mark.asyncio
async def test_failed_page_does_not_block_candidate_merge(tmp_path, monkeypatch):
    workspace_id = f"large-pdf-failure-{uuid.uuid4().hex}"
    settings = _settings(tmp_path, pdf_page_max_attempts=2)
    storage = SourceFileStorage(settings.source_files_dir)
    pending = storage.state_dir("pending") / "partial.pdf"
    pending.write_bytes(_pdf_bytes(3))

    async def fake_parse(page_bytes, filename, doc_id, parser_settings):
        if ".page-2.pdf" in filename:
            raise RuntimeError("simulated page failure")
        return ParsedMarkdown(
            markdown=f"---\ndoc_id: {doc_id}\n---\n\n{filename}", confidence=0.8
        )

    monkeypatch.setattr("app.api.routes.knowledge._parse_pdf_to_markdown", fake_parse)
    factory = get_session_factory()
    source_id = document_id = None
    try:
        async with factory() as session:
            _, source = await SourceIngestionService(session, settings).register_uploaded(
                pending, workspace_id, "default"
            )
            source_id = source.id
            document_id = source.knowledge_document_id
            job = (
                await session.execute(
                    select(KnowledgeIngestionJobModel).where(
                        KnowledgeIngestionJobModel.source_file_id == source.id
                    )
                )
            ).scalar_one()
            job_id = job.id

        await IngestionExecutor(factory, settings)._process(job_id)

        async with factory() as session:
            job = await session.get(KnowledgeIngestionJobModel, job_id)
            document = await session.get(KnowledgeDocumentModel, document_id)
            assert job.status == "completed_with_errors"
            assert (job.succeeded_pages, job.failed_pages) == (2, 1)
            candidate = (tmp_path / "documents" / f"{document_id}.candidate.md").read_text(
                encoding="utf-8"
            )
            assert "第 2 页识别失败" in candidate
            assert (
                candidate.index("source-page: 1")
                < candidate.index("source-page: 2")
                < candidate.index("source-page: 3")
            )
            assert document.status == "awaiting_confirmation"
    finally:
        await _cleanup(factory, source_id, document_id)
