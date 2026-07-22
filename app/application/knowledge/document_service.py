from uuid import UUID
from app.domain.knowledge import KnowledgeDocumentStatus, SourceType


class DocumentService:
    @staticmethod
    def determine_initial_status(source_type: SourceType | str) -> KnowledgeDocumentStatus:
        if isinstance(source_type, str):
            try:
                source_type = SourceType(source_type.lower())
            except ValueError:
                return KnowledgeDocumentStatus.AWAITING_CONFIRMATION

        if source_type == SourceType.MARKDOWN:
            return KnowledgeDocumentStatus.INDEXING
        return KnowledgeDocumentStatus.AWAITING_CONFIRMATION
