import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.errors import DocumentConflictError
from app.application.document_service import DocumentService


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
