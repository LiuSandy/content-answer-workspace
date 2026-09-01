from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.platform.database import Base
from app.modules.acquisition.adapters.db.models import SourceItem
from app.modules.documents.adapters.db.models import AIOperation, AnswerDocument
from app.modules.writing.agent.nodes.full_rewrite import full_rewrite_workflow


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "TEXT"


@pytest.mark.asyncio
async def test_full_rewrite_uses_restored_content_and_selected_outline(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    db = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with db() as session:
        source = SourceItem(
            platform="zhihu",
            external_id="rewrite-outline",
            url="https://example.test/rewrite-outline",
            title="问题",
            content="问题描述",
        )
        session.add(source)
        await session.flush()
        document = AnswerDocument(source_item_id=source.id, current_content="恢复后的文章 V1")
        session.add(document)
        await session.flush()
        outline = AIOperation(
            document_id=document.id,
            operation_type="outline",
            status="completed",
            input_metadata={
                "outlineStatus": "confirmed",
                "outlineVersion": 1,
                "outline": [
                    {"heading": "保留的结构", "keyPoints": ["关键点"], "wordCountEstimate": 300}
                ],
            },
        )
        session.add(outline)
        await session.flush()
        document.current_outline_operation_id = outline.id
        await session.commit()

        observed_variables = {}
        observed_writer_kwargs = {}

        def fake_render(prompt_id, **kwargs):
            observed_variables["prompt_id"] = prompt_id
            observed_variables.update(kwargs)
            return MagicMock(messages=[])

        async def fake_writer_stream(*args, **kwargs):
            observed_writer_kwargs.update(kwargs)
            yield "rewritten"

        monkeypatch.setattr(
            "app.modules.writing.agent.nodes.full_rewrite.compose_writing_prompt",
            lambda *args, **kwargs: MagicMock(messages=[]),
        )
        monkeypatch.setattr(
            "app.modules.writing.agent.nodes.full_rewrite.prompt_registry.render", fake_render
        )
        monkeypatch.setattr(
            "app.modules.writing.agent.nodes.full_rewrite.run_writer_stream", fake_writer_stream
        )

        parts = [part async for part in full_rewrite_workflow(
            session=session,
            document_id=document.id,
            instruction="进一步润色",
            expected_lock_version=document.lock_version,
        )]

        assert parts == ["rewritten"]
        assert observed_variables["prompt_id"] == "writing.user_rewrite"
        assert observed_variables["current_answer"] == "恢复后的文章 V1"
        assert "保留的结构" in observed_variables["outline"]
        assert observed_writer_kwargs["outline_operation_id"] == outline.id

    await engine.dispose()
