import pytest
from app.modules.knowledge.domain.models import KnowledgeDocumentStatus, SourceType
from app.modules.knowledge.application.document_service import DocumentService

def test_determine_initial_status():
    md_status = DocumentService.determine_initial_status(SourceType.MARKDOWN)
    assert md_status == KnowledgeDocumentStatus.INDEXING

    pdf_status = DocumentService.determine_initial_status(SourceType.PDF)
    assert pdf_status == KnowledgeDocumentStatus.AWAITING_CONFIRMATION

    url_status = DocumentService.determine_initial_status(SourceType.URL)
    assert url_status == KnowledgeDocumentStatus.AWAITING_CONFIRMATION
