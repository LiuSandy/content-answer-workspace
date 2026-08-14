"""R7 写作服务与创作背景测试：三操作统一、锁冲突重试、上下文拼装、素材隔离。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.services.context.writing_background import WritingBackground
from app.services.document_service import DocumentService
from app.services.writing_service import (
    WriterRunCapture,
    _version_type_for,
    finalize_deferred_writer_run,
    run_writer_stream,
)
from app.contracts.knowledge import SourceType
from app.infrastructure.database import Base
from app.infrastructure.database.models.content import SourceItem
from app.infrastructure.database.models.documents import AIOperation, AnswerDocument, AnswerVersion

from app.prompts.registry import prompt_registry, RenderedPrompt


@compiles(JSONB, "sqlite")
def _c(type_, compiler, **kw):
    return "TEXT"


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession), engine


async def _setup_doc(db) -> tuple[uuid.UUID, uuid.UUID]:
    async with db() as session:
        si = SourceItem(id=uuid.uuid4(), platform="zhihu", external_id="x", url="u", title="T", content="C")
        session.add(si)
        doc = AnswerDocument(id=uuid.uuid4(), source_item_id=si.id)
        session.add(doc)
        await session.commit()
        return doc.id, si.id


def _fake_rendered():
    from app.prompts.registry import RenderedPrompt
    from app.contracts.dto import LLMMessage
    return RenderedPrompt(
        prompt_id="test",
        messages=[LLMMessage(role="system", content="system"), LLMMessage(role="user", content="user")],
        model="deepseek-v4-pro",
        temperature=0.7,
        max_tokens=100,
    )


def _mock_provider(monkeypatch, content="streamed text"):
    fake = MagicMock()
    fake.key = "deepseek"
    fake.stream = MagicMock()
    async def _event_gen():
        from types import SimpleNamespace
        yield SimpleNamespace(delta=content, input_tokens=10, output_tokens=5)
    fake.stream.return_value = _event_gen()
    monkeypatch.setattr(
        "app.services.writing_service.llm_provider_registry.get",
        lambda _k: fake,
    )
    return fake


async def _version_count(session: AsyncSession, document_id: uuid.UUID) -> int:
    rows = (
        await session.execute(
            select(AnswerVersion).where(AnswerVersion.document_id == document_id)
        )
    ).scalars().all()
    return len(rows)


@pytest.mark.asyncio
async def test_version_type_mapping():
    assert _version_type_for("generate") == "initial_generation"
    assert _version_type_for("refine") == "inline_refinement"
    assert _version_type_for("full_rewrite") == "full_rewrite"
    assert _version_type_for("unknown") == "initial_generation"


@pytest.mark.asyncio
async def test_run_writer_stream_generate(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    rendered = _fake_rendered()
    _mock_provider(monkeypatch)

    async with db() as session:
        parts = []
        async for delta in run_writer_stream(session, "generate", doc_id, rendered, 1):
            parts.append(delta)
        assert parts == ["streamed text"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_run_writer_stream_refine_with_assembler(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    rendered = _fake_rendered()
    _mock_provider(monkeypatch, content="REPLACED")

    async with db() as session:
        parts = []
        async for delta in run_writer_stream(
            session, "refine", doc_id, rendered, 1,
            content_assembler=lambda parts: "BEFORE_" + "".join(parts) + "_AFTER",
        ):
            parts.append(delta)
        assert parts == ["REPLACED"]

        # 验证版本保存了完整内容
        from sqlalchemy import select
        from app.infrastructure.database.models.documents import AnswerVersion
        versions = (await session.execute(
            select(AnswerVersion).where(AnswerVersion.document_id == doc_id)
        )).scalars().all()
        assert len(versions) == 1
        assert versions[0].content == "BEFORE_REPLACED_AFTER"

    await engine.dispose()


@pytest.mark.asyncio
async def test_run_writer_stream_full_rewrite(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    rendered = _fake_rendered()
    _mock_provider(monkeypatch, content="rewritten")

    async with db() as session:
        parts = []
        async for delta in run_writer_stream(
            session, "full_rewrite", doc_id, rendered, 1,
            version_extra={"instruction": "改写"},
        ):
            parts.append(delta)
        assert parts == ["rewritten"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_deferred_writer_creates_exactly_one_final_version(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    _mock_provider(monkeypatch, content="internal draft")
    capture = WriterRunCapture()

    async with db() as session:
        parts = [part async for part in run_writer_stream(
            session,
            "generate",
            doc_id,
            _fake_rendered(),
            1,
            defer_version=True,
            capture=capture,
        )]

        assert parts == ["internal draft"]
        assert capture.content == "internal draft"
        assert await _version_count(session, doc_id) == 0

        operation = await session.get(AIOperation, capture.operation_id)
        assert operation is not None
        assert operation.status == "running"
        assert operation.result_version_id is None

        version = await finalize_deferred_writer_run(
            session=session,
            capture=capture,
            final_content="reviewed final",
            expected_lock_version=1,
            output_metadata={"creationReview": {"iterations": 3}},
        )

        assert version.content == "reviewed final"
        assert await _version_count(session, doc_id) == 1
        await session.refresh(operation)
        assert operation.status == "completed"
        assert operation.result_version_id == version.id
        assert operation.output_metadata == {"creationReview": {"iterations": 3}}

    await engine.dispose()


@pytest.mark.asyncio
async def test_deferred_writer_links_final_version_to_selected_outline(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    outline_operation_id = uuid.uuid4()
    capture = WriterRunCapture(
        operation_id=uuid.uuid4(),
        document_id=doc_id,
        content="draft",
        outline_operation_id=outline_operation_id,
    )

    async with db() as session:
        session.add(AIOperation(
            id=capture.operation_id,
            document_id=doc_id,
            operation_type="generate",
            status="running",
        ))
        await session.commit()
        version = await finalize_deferred_writer_run(
            session=session,
            capture=capture,
            final_content="final",
            expected_lock_version=1,
            output_metadata={},
        )
        assert version.outline_operation_id == outline_operation_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_version_summary_includes_content_outline_and_review(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    outline_id = uuid.uuid4()

    async with db() as session:
        session.add(AIOperation(
            id=outline_id,
            document_id=doc_id,
            operation_type="outline",
            status="completed",
            input_metadata={
                "outlineVersion": 3,
                "outlineStatus": "confirmed",
                "outline": [
                    {"heading": "核心结构", "keyPoints": ["论据"], "wordCountEstimate": 300}
                ],
            },
        ))
        await session.commit()
        version = await DocumentService(session).create_version(
            document_id=doc_id,
            content="第一段内容。\n\n第二段内容，用于验证历史版本摘要。",
            version_type="initial_generation",
            expected_lock_version=1,
            provider="deepseek",
            model="deepseek-v4-pro",
            outline_operation_id=outline_id,
        )
        session.add(AIOperation(
            document_id=doc_id,
            operation_type="generate",
            status="completed",
            result_version_id=version.id,
            output_metadata={
                "creationReview": {
                    "iterations": 2,
                    "passed": True,
                    "selectedIteration": 2,
                    "reviewStatus": "completed",
                    "rounds": [
                        {"iteration": 1, "overallScore": 70, "passed": False},
                        {"iteration": 2, "overallScore": 86, "passed": True},
                    ],
                    "finalReport": {
                        "overallScore": 86,
                        "dimensionScores": {
                            "relevance": 90,
                            "information_density": 84,
                            "readability": 86,
                            "logic_coherence": 85,
                            "word_count_compliance": 88,
                        },
                        "issues": [],
                        "suggestions": ["保持当前结构"],
                        "summary": "整体质量良好",
                    },
                }
            },
        ))
        await session.commit()

        summary = (await DocumentService(session).list_versions(doc_id))[0]
        assert summary.content_summary == "第一段内容。 第二段内容，用于验证历史版本摘要。"
        assert summary.outline_version_number == 3
        assert summary.outline_status == "confirmed"
        assert summary.outline_sections[0]["heading"] == "核心结构"
        assert summary.quality_review["overallScore"] == 86
        assert summary.quality_review["summary"] == "整体质量良好"

    await engine.dispose()


@pytest.mark.asyncio
async def test_current_legacy_version_falls_back_to_latest_document_outline(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)

    async with db() as session:
        version = await DocumentService(session).create_version(
            document_id=doc_id,
            content="旧版本正文",
            version_type="initial_generation",
            expected_lock_version=1,
        )
        outline = AIOperation(
            document_id=doc_id,
            operation_type="outline",
            status="completed",
            input_metadata={
                "outlineStatus": "draft",
                "outline": [
                    {"heading": "后补的大纲", "keyPoints": ["要点"], "wordCountEstimate": 200}
                ],
            },
        )
        session.add(outline)
        await session.commit()

        summaries = await DocumentService(session).list_versions(doc_id)
        assert summaries[0].id == str(version.id)
        assert summaries[0].outline_operation_id == str(outline.id)
        assert summaries[0].outline_version_number == 1
        assert summaries[0].outline_sections[0]["heading"] == "后补的大纲"

    await engine.dispose()


@pytest.mark.asyncio
async def test_deferred_writer_requires_capture(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    _mock_provider(monkeypatch)

    async with db() as session:
        with pytest.raises(ValueError, match="capture"):
            _ = [part async for part in run_writer_stream(
                session,
                "generate",
                doc_id,
                _fake_rendered(),
                1,
                defer_version=True,
            )]

    await engine.dispose()


@pytest.mark.asyncio
async def test_finalize_deferred_writer_retries_lock_conflict_without_duplicate_version(monkeypatch):
    db, engine = await _make_db()
    doc_id, _ = await _setup_doc(db)
    _mock_provider(monkeypatch, content="internal draft")
    capture = WriterRunCapture()

    async with db() as generation_session:
        _ = [part async for part in run_writer_stream(
            generation_session,
            "generate",
            doc_id,
            _fake_rendered(),
            1,
            defer_version=True,
            capture=capture,
        )]

        async with db() as competing_session:
            from app.services.document_service import DocumentService

            await DocumentService(competing_session).update_content(
                doc_id, "concurrent edit", expected_lock_version=1
            )

        version = await finalize_deferred_writer_run(
            session=generation_session,
            capture=capture,
            final_content="reviewed final",
            expected_lock_version=1,
            output_metadata={},
        )

        assert version.version_number == 1
        assert await _version_count(generation_session, doc_id) == 1
        operation = await generation_session.get(AIOperation, capture.operation_id)
        assert operation is not None
        assert operation.status == "completed"
        assert operation.result_version_id == version.id

    await engine.dispose()


# ── 创作背景 ──────────────────────────────────────────────────────────────


def test_writing_background_assembles_with_priority():
    bg = WritingBackground(
        confirmed_outline=[{"heading": "H", "keyPoints": ["kp"]}],
        active_memories=[{"memory_type": "explicit", "content": "喜欢简洁"}],
        dialog_background="对话历史摘要...",
        material_context="素材检索结果...",
        platform_style_guide="平台偏好正式语气。",
    )
    text = bg.to_context_text()
    # 确认大纲在平台风格之前
    assert text.index("已确认的创作大纲") < text.index("平台风格指南")
    # L2 记忆在对话背景之前
    assert text.index("长期偏好") < text.index("对话背景")
    # 至少包含关键块
    assert "已确认" in text


def test_writing_background_empty_returns_empty():
    assert WritingBackground().to_context_text() == ""


# ── 素材类型 ──────────────────────────────────────────────────────────────


def test_source_type_has_material():
    assert SourceType.MATERIAL == "material"
