from uuid import UUID
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.contracts.knowledge import KnowledgeDocumentStatus, SourceType
from app.infrastructure.database.models.knowledge import KnowledgeDocumentModel
from app.infrastructure.database.repositories.knowledge_storage import KnowledgeStorage

class DocumentService:
    def __init__(self, session: AsyncSession, storage: KnowledgeStorage):
        self.session = session
        self.storage = storage

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

    async def create_from_upload(self, file_bytes: bytes, filename: str, source_type: str, workspace_id: str, owner_id: str) -> tuple[KnowledgeDocumentModel, bool]:
        """创建上传文档；按内容 hash 去重。

        返回 (文档, 是否新建)——去重命中时调用方必须短路，
        不能对已存在（可能已确认索引）的文档重新解析覆盖候选稿。
        """
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        stmt = select(KnowledgeDocumentModel).where(
            KnowledgeDocumentModel.workspace_id == workspace_id,
            KnowledgeDocumentModel.source_content_hash == content_hash,
            KnowledgeDocumentModel.status != KnowledgeDocumentStatus.DELETED.value
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing, False

        doc = KnowledgeDocumentModel(
            workspace_id=workspace_id,
            owner_id=owner_id,
            title=filename,
            source_type=source_type,
            status=self.determine_initial_status(source_type).value,
            source_content_hash=content_hash
        )
        self.session.add(doc)
        await self.session.flush()
        
        if source_type.lower() != SourceType.MARKDOWN.value:
            saved_path = self.storage.save_source(doc.id, filename, file_bytes)
            doc.source_path = str(saved_path)
        else:
            saved_path = self.storage.publish_markdown(doc.id, file_bytes.decode('utf-8', errors='ignore'))
            doc.markdown_path = str(saved_path)
            doc.markdown_content_hash = content_hash
            
        await self.session.commit()
        return doc, True

    async def create_from_url(self, url: str, workspace_id: str, owner_id: str) -> KnowledgeDocumentModel:
        doc = KnowledgeDocumentModel(
            workspace_id=workspace_id,
            owner_id=owner_id,
            title=url,
            source_type=SourceType.URL.value,
            source_url=url,
            status=KnowledgeDocumentStatus.AWAITING_CONFIRMATION.value
        )
        self.session.add(doc)
        await self.session.commit()
        return doc

    async def save_candidate_markdown(
        self,
        doc_id: UUID,
        markdown: str,
        workspace_id: str,
        confidence: float | None = None,
    ) -> KnowledgeDocumentModel:
        doc = await self.get_document(doc_id, workspace_id)
        if not doc:
            raise ValueError("Document not found")

        path = self.storage.save_candidate(doc_id, markdown)
        doc.candidate_markdown_path = str(path)
        if confidence is not None:
            doc.conversion_confidence = confidence
        await self.session.commit()
        return doc

    async def confirm_document(self, doc_id: UUID, workspace_id: str) -> KnowledgeDocumentModel:
        doc = await self.get_document(doc_id, workspace_id)
        if not doc:
            raise ValueError("Document not found")
            
        candidate_md = self.storage.read_markdown(doc_id, is_candidate=True)
        if candidate_md is None:
            raise ValueError("Candidate markdown not found")
            
        path = self.storage.publish_markdown(doc_id, candidate_md)
        doc.markdown_path = str(path)
        doc.markdown_content_hash = hashlib.sha256(candidate_md.encode('utf-8')).hexdigest()
        doc.status = KnowledgeDocumentStatus.INDEXING.value
        doc.has_manual_edits = True
        # 候选稿阶段已记录的 conversion_confidence 原样保留,不因"确认"动作被清空或重置为 1.0
        await self.session.commit()
        return doc

    async def save_active_markdown(
        self,
        doc_id: UUID,
        markdown: str,
        workspace_id: str,
        confidence: float | None = None,
    ) -> KnowledgeDocumentModel:
        doc = await self.get_document(doc_id, workspace_id)
        if not doc:
            raise ValueError("Document not found")

        path = self.storage.publish_markdown(doc_id, markdown)
        doc.markdown_path = str(path)
        doc.markdown_content_hash = hashlib.sha256(markdown.encode('utf-8')).hexdigest()
        doc.status = KnowledgeDocumentStatus.INDEXING.value
        if confidence is not None:
            doc.conversion_confidence = confidence
        await self.session.commit()
        return doc

    async def get_markdown(self, doc_id: UUID, workspace_id: str, is_candidate: bool = False) -> str | None:
        return self.storage.read_markdown(doc_id, is_candidate=is_candidate)

    async def soft_delete(self, doc_id: UUID, workspace_id: str) -> None:
        doc = await self.get_document(doc_id, workspace_id)
        if doc:
            doc.status = KnowledgeDocumentStatus.DELETED.value
            await self.session.commit()

    async def get_document(self, doc_id: UUID, workspace_id: str) -> KnowledgeDocumentModel | None:
        stmt = select(KnowledgeDocumentModel).where(
            KnowledgeDocumentModel.id == doc_id,
            KnowledgeDocumentModel.workspace_id == workspace_id,
            KnowledgeDocumentModel.status != KnowledgeDocumentStatus.DELETED.value
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_documents(
        self, workspace_id: str, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[KnowledgeDocumentModel], int]:
        """分页列出文档；返回 (当前页文档, 满足条件的总数)。

        total 用独立 count 查询而非 len(当前页)，否则前端分页会错。
        """
        conditions = [
            KnowledgeDocumentModel.workspace_id == workspace_id,
            KnowledgeDocumentModel.status != KnowledgeDocumentStatus.DELETED.value,
        ]
        if status:
            conditions.append(KnowledgeDocumentModel.status == status)

        count_stmt = select(func.count()).select_from(KnowledgeDocumentModel).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(KnowledgeDocumentModel)
            .where(*conditions)
            .order_by(KnowledgeDocumentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        docs = list((await self.session.execute(stmt)).scalars().all())
        return docs, total
