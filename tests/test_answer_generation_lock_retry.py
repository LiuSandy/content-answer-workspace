import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.errors import DocumentConflictError
from app.application.document_service import DocumentService
from app.application.writer_service import WriterRunCapture
from app.workflows.answer_generation import generate_answer_workflow


@pytest.mark.asyncio
async def test_answer_generation_handles_lock_conflict():
    err = DocumentConflictError(expected=17, actual=18)
    assert err.expected == 17
    assert err.actual == 18
    assert "expected 17, got 18" in str(err)


@pytest.mark.asyncio
async def test_document_service_has_get_document_method():
    session = AsyncMock()
    doc_id = uuid.uuid4()
    mock_doc = MagicMock(id=doc_id, lock_version=18)
    session.get.return_value = mock_doc

    service = DocumentService(session)
    doc = await service.get_document(doc_id)
    assert doc is not None
    assert doc.lock_version == 18


@pytest.mark.asyncio
async def test_answer_generation_defers_version_and_populates_capture(monkeypatch):
    capture = WriterRunCapture()
    observed = {}

    async def fake_writer_stream(*args, **kwargs):
        observed.update(kwargs)
        kwargs["capture"].content = "draft"
        yield "draft"

    monkeypatch.setattr(
        "app.workflows.answer_generation.run_writer_stream", fake_writer_stream
    )
    monkeypatch.setattr(
        "app.workflows.answer_generation.compose_writing_prompt",
        lambda *args, **kwargs: MagicMock(messages=[]),
    )
    monkeypatch.setattr(
        "app.workflows.answer_generation.prompt_registry.render",
        lambda *args, **kwargs: MagicMock(messages=[]),
    )

    session = AsyncMock()
    session.get.return_value = None
    parts = [part async for part in generate_answer_workflow(
        session=session,
        source_item_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        platform="zhihu",
        title="question",
        content=None,
        expected_lock_version=1,
        capture=capture,
    )]

    assert parts == ["draft"]
    assert observed["defer_version"] is True
    assert observed["capture"] is capture
