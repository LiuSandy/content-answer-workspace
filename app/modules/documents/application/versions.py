"""
Version Service：管理历史版本的手动创建与恢复，代理调用 DocumentService。
"""
from __future__ import annotations

import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from .documents import DocumentService
from app.modules.documents.adapters.db.models import VERSION_TYPE_MANUAL_CHECKPOINT, AnswerVersion
from app.shared.dto import VersionSummaryDTO


class VersionService:
    def __init__(self, session: AsyncSession) -> None:
        self._doc_service = DocumentService(session)

    async def list_versions(self, document_id: uuid.UUID) -> list[VersionSummaryDTO]:
        return await self._doc_service.list_versions(document_id)

    async def create_manual_checkpoint(
        self,
        document_id: uuid.UUID,
        expected_lock_version: int,
    ) -> AnswerVersion:
        doc = await self._doc_service._get_doc_or_raise(document_id)
        if not doc.current_content:
            raise ValueError("Cannot checkpoint empty document")

        return await self._doc_service.create_version(
            document_id=document_id,
            content=doc.current_content,
            version_type=VERSION_TYPE_MANUAL_CHECKPOINT,
            expected_lock_version=expected_lock_version,
        )

    async def restore_version(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        expected_lock_version: int,
    ) -> AnswerVersion:
        return await self._doc_service.restore_version(
            document_id=document_id,
            version_id=version_id,
            expected_lock_version=expected_lock_version,
        )
