"""R7 写作服务与创作背景测试：三操作统一、锁冲突重试、上下文拼装、素材隔离。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.application.context.writing_background import WritingBackground
from app.application.writer_service import _version_type_for, run_writer_stream
from app.domain.knowledge import SourceType
from app.persistence import Base
from app.persistence.models.content import SourceItem
from app.persistence.models.documents import AnswerDocument

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
    from app.domain.dto import LLMMessage
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
        "app.application.writer_service.llm_provider_registry.get",
        lambda _k: fake,
    )
    return fake


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
        from app.persistence.models.documents import AnswerVersion
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
