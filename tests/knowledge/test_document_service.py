import pytest
from app.domain.knowledge import KnowledgeDocumentStatus, SourceType
from app.application.knowledge.document_service import DocumentService


def test_document_status_transitions():
    # Markdown 上传：初始即索引或可用
    md_status = DocumentService.determine_initial_status(SourceType.MARKDOWN)
    assert md_status == KnowledgeDocumentStatus.INDEXING

    # 非 Markdown 上传：待确认
    pdf_status = DocumentService.determine_initial_status(SourceType.PDF)
    assert pdf_status == KnowledgeDocumentStatus.AWAITING_CONFIRMATION

    url_status = DocumentService.determine_initial_status(SourceType.URL)
    assert url_status == KnowledgeDocumentStatus.AWAITING_CONFIRMATION
