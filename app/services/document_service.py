"""
Document Service：管理 AnswerDocument 和乐观锁。
所有内容更新和保存版本必须携带 expected_lock_version。
"""
from __future__ import annotations

import uuid
import re
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.errors import DocumentConflictError
from app.infrastructure.database.models.documents import AIOperation, AnswerDocument, AnswerVersion
from app.infrastructure.database.models.content import SourceItem
from app.contracts.dto import DocumentStateDTO, VersionSummaryDTO, SourceItemInfoDTO


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_document(self, document_id: uuid.UUID) -> AnswerDocument | None:
        return await self._session.get(AnswerDocument, document_id)

    async def get_or_create_document(self, source_item_id: uuid.UUID) -> AnswerDocument:
        result = await self._session.execute(
            select(AnswerDocument).where(AnswerDocument.source_item_id == source_item_id)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            doc = AnswerDocument(
                id=uuid.uuid4(),
                source_item_id=source_item_id,
                current_content=None,
                lock_version=1,
            )
            self._session.add(doc)
            await self._session.commit()
            await self._session.refresh(doc)
        return doc

    async def update_content(
        self,
        document_id: uuid.UUID,
        content: str,
        expected_lock_version: int,
    ) -> AnswerDocument:
        """自动保存（Auto-save）：仅更新 current_content 并自增 lock_version，不产生新的历史版本。"""
        doc = await self._get_doc_or_raise(document_id)
        self._check_lock(doc, expected_lock_version)

        doc.current_content = content
        doc.lock_version += 1
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def create_version(
        self,
        document_id: uuid.UUID,
        content: str,
        version_type: str,
        expected_lock_version: int,
        instruction: str | None = None,
        restored_from_version_id: uuid.UUID | None = None,
        prompt_id: str | None = None,
        prompt_version: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        outline_operation_id: uuid.UUID | None = None,
    ) -> AnswerVersion:
        """正式保存（AI 生成/润色/手动保存/恢复等）：更新 Document，并创建完整版本快照。"""
        doc = await self._get_doc_or_raise(document_id)
        self._check_lock(doc, expected_lock_version)

        # 获取当前最大的版本号
        result = await self._session.execute(
            select(AnswerVersion)
            .where(AnswerVersion.document_id == document_id)
            .order_by(AnswerVersion.version_number.desc())
            .limit(1)
        )
        last_version = result.scalar_one_or_none()
        new_version_number = (last_version.version_number + 1) if last_version else 1

        # 创建新版本快照
        version = AnswerVersion(
            id=uuid.uuid4(),
            document_id=document_id,
            version_number=new_version_number,
            content=content,
            version_type=version_type,
            instruction=instruction,
            restored_from_version_id=restored_from_version_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider=provider,
            model=model,
            outline_operation_id=outline_operation_id or doc.current_outline_operation_id,
        )
        self._session.add(version)
        await self._session.flush()

        # 同一事务中更新 Document 的 current_content 和 current_version_id
        doc.current_content = content
        doc.current_version_id = version.id
        doc.lock_version += 1

        await self._session.commit()
        await self._session.refresh(version)
        return version

    async def list_versions(self, document_id: uuid.UUID) -> list[VersionSummaryDTO]:
        """获取历史版本卡片所需的只读摘要、大纲快照与评审报告。"""
        result = await self._session.execute(
            select(AnswerVersion)
            .where(AnswerVersion.document_id == document_id)
            .order_by(AnswerVersion.version_number.desc())
        )
        versions = result.scalars().all()

        document = await self._session.get(AnswerDocument, document_id)
        all_outline_operations = list(
            (
                await self._session.execute(
                    select(AIOperation)
                    .where(AIOperation.document_id == document_id)
                    .where(AIOperation.operation_type == "outline")
                    .where(AIOperation.status == "completed")
                    .order_by(AIOperation.created_at.asc(), AIOperation.id.asc())
                )
            ).scalars().all()
        )
        outline_version_numbers: dict[uuid.UUID, int] = {}
        used_outline_numbers: set[int] = set()
        for index, operation in enumerate(all_outline_operations, 1):
            stored_number = (operation.input_metadata or {}).get("outlineVersion")
            number = stored_number if isinstance(stored_number, int) and stored_number > 0 else index
            while number in used_outline_numbers:
                number += 1
            outline_version_numbers[operation.id] = number
            used_outline_numbers.add(number)

        fallback_outline_id = (
            document.current_outline_operation_id if document is not None else None
        )
        if fallback_outline_id is None:
            latest_outline = all_outline_operations[-1] if all_outline_operations else None
            fallback_outline_id = latest_outline.id if latest_outline else None

        effective_outline_ids = {
            version.id: (
                version.outline_operation_id
                or (
                    fallback_outline_id
                    if document is not None
                    and version.id == document.current_version_id
                    else None
                )
            )
            for version in versions
        }
        outline_ids = {value for value in effective_outline_ids.values() if value}
        outlines: dict[uuid.UUID, AIOperation] = {}
        if outline_ids:
            outline_rows = (
                await self._session.execute(
                    select(AIOperation).where(AIOperation.id.in_(outline_ids))
                )
            ).scalars().all()
            outlines = {row.id: row for row in outline_rows}

        from .quality_service import (
            _map_creation_review_operation,
            _map_legacy_review_operation,
        )

        review_operations = (
            await self._session.execute(
                select(AIOperation)
                .where(AIOperation.document_id == document_id)
                .where(AIOperation.status == "completed")
                .where(AIOperation.operation_type.in_(("generate", "quality_review")))
                .order_by(AIOperation.created_at.desc())
            )
        ).scalars().all()
        reviews_by_version: dict[str, dict] = {}
        for operation in review_operations:
            if operation.operation_type == "generate":
                creation_review = (operation.output_metadata or {}).get(
                    "creationReview"
                )
                if operation.result_version_id and isinstance(creation_review, dict):
                    reviews_by_version.setdefault(
                        str(operation.result_version_id),
                        _map_creation_review_operation(operation, creation_review),
                    )
                continue
            report = (operation.output_metadata or {}).get("report")
            source_version_id = (operation.input_metadata or {}).get(
                "sourceVersionId"
            )
            if source_version_id and isinstance(report, dict):
                reviews_by_version.setdefault(
                    str(source_version_id),
                    _map_legacy_review_operation(operation, report),
                )

        def summarize(content: str) -> str:
            plain = re.sub(r"<[^>]+>", " ", content)
            plain = re.sub(r"\s+", " ", plain).strip()
            return plain[:180]

        return [
            VersionSummaryDTO(
                id=str(v.id),
                version_number=v.version_number,
                version_type=v.version_type,
                instruction=v.instruction,
                provider=v.provider,
                model=v.model,
                outline_operation_id=(
                    str(effective_outline_ids[v.id])
                    if effective_outline_ids[v.id]
                    else None
                ),
                content_summary=summarize(v.content),
                outline_version_number=(
                    outline_version_numbers.get(effective_outline_ids[v.id])
                    if effective_outline_ids[v.id] in outlines
                    else None
                ),
                outline_status=(
                    (outlines[effective_outline_ids[v.id]].input_metadata or {}).get(
                        "outlineStatus"
                    )
                    if effective_outline_ids[v.id] in outlines
                    else None
                ),
                outline_sections=(
                    (outlines[effective_outline_ids[v.id]].input_metadata or {}).get(
                        "outline"
                    )
                    or []
                    if effective_outline_ids[v.id] in outlines
                    else []
                ),
                quality_review=reviews_by_version.get(str(v.id)),
                created_at=v.created_at,
            )
            for v in versions
        ]

    async def restore_version(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        expected_lock_version: int,
    ) -> AnswerVersion:
        """恢复特定版本：语义等价于 Git reset——只把 Document 指针指回该历史版本，
        不创建新的 AnswerVersion 记录，因此历史版本列表数量和编号保持不变。
        """
        doc = await self._get_doc_or_raise(document_id)
        self._check_lock(doc, expected_lock_version)

        source_version = await self._session.get(AnswerVersion, version_id)
        if source_version is None or str(source_version.document_id) != str(document_id):
            raise ValueError(f"Version {version_id} not found in document {document_id}")

        doc.current_content = source_version.content
        doc.current_version_id = source_version.id
        if source_version.outline_operation_id is not None:
            doc.current_outline_operation_id = source_version.outline_operation_id
        doc.lock_version += 1

        await self._session.commit()
        await self._session.refresh(source_version)
        return source_version

    async def get_document_state(self, document_id: uuid.UUID) -> DocumentStateDTO | None:
        """获取当前文档的最新状态，包含关联帖子的原文元数据。"""
        doc = await self._get_doc_or_raise(document_id)
        
        # 查询关联的 SourceItem
        source_item = await self._session.get(SourceItem, doc.source_item_id)
        source_item_info = None
        if source_item:
            source_item_info = SourceItemInfoDTO(
                title=source_item.title,
                content=source_item.content,
                url=source_item.url,
                platform=source_item.platform,
                author=source_item.author,
            )

        return DocumentStateDTO(
            document_id=str(doc.id),
            source_item_id=str(doc.source_item_id),
            current_content=doc.current_content,
            current_version_id=str(doc.current_version_id) if doc.current_version_id else None,
            lock_version=doc.lock_version,
            updated_at=doc.updated_at,
            source_item=source_item_info,
        )

    # ── 内部辅助 ──

    async def _get_doc_or_raise(self, document_id: uuid.UUID) -> AnswerDocument:
        doc = await self._session.get(AnswerDocument, document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        return doc

    def _check_lock(self, doc: AnswerDocument, expected: int) -> None:
        if doc.lock_version != expected:
            raise DocumentConflictError(expected=expected, actual=doc.lock_version)
