from typing import Sequence
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.persistence.models.knowledge import KnowledgeDocumentModel, KnowledgeChunkModel, RetrievalTraceModel, RetrievalHitModel
from app.domain.knowledge import KnowledgeDocumentStatus


class KnowledgeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_document(self, doc: KnowledgeDocumentModel) -> KnowledgeDocumentModel:
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get_document_by_id(self, doc_id: UUID, workspace_id: str | None = None) -> KnowledgeDocumentModel | None:
        query = select(KnowledgeDocumentModel).where(
            KnowledgeDocumentModel.id == doc_id,
            KnowledgeDocumentModel.deleted_at.is_(None)
        )
        if workspace_id:
            query = query.where(KnowledgeDocumentModel.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_documents(
        self, workspace_id: str, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> Sequence[KnowledgeDocumentModel]:
        query = select(KnowledgeDocumentModel).where(
            KnowledgeDocumentModel.workspace_id == workspace_id,
            KnowledgeDocumentModel.deleted_at.is_(None)
        ).order_by(KnowledgeDocumentModel.created_at.desc())
        
        if status:
            query = query.where(KnowledgeDocumentModel.status == status)

        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update_status(self, doc_id: UUID, status: str, error: str | None = None) -> None:
        stmt = (
            update(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.id == doc_id)
            .values(status=status, conversion_error=error, updated_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def soft_delete_document(self, doc_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        stmt = (
            update(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.id == doc_id)
            .values(status=KnowledgeDocumentStatus.DELETED.value, deleted_at=now, updated_at=now)
        )
        await self.session.execute(stmt)
        
        # 联动软删除 Chunk
        chunk_stmt = (
            update(KnowledgeChunkModel)
            .where(KnowledgeChunkModel.document_id == doc_id)
            .values(deleted_at=now)
        )
        await self.session.execute(chunk_stmt)
