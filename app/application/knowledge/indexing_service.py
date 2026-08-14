from __future__ import annotations
import uuid
import logging
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.domain.knowledge import KnowledgeDocumentStatus, ChunkType, KnowledgeScope
from app.persistence.models.knowledge import KnowledgeDocumentModel, KnowledgeChunkModel
from app.application.knowledge.chunking import ParentChildChunker
from app.application.knowledge.context_builder import estimate_tokens
from app.infrastructure.knowledge.embedding import get_embedding_provider
from app.infrastructure.knowledge.storage import KnowledgeStorage
from app.core.config import get_knowledge_settings

logger = logging.getLogger(__name__)

@dataclass
class IndexResult:
    document_id: UUID
    index_version: str
    parent_count: int
    child_count: int
    success: bool
    error: str | None = None

class IndexingService:
    def __init__(self, session: AsyncSession, storage: KnowledgeStorage):
        self.session = session
        self.storage = storage

    @staticmethod
    def generate_index_version() -> str:
        return f"v_{uuid.uuid4().hex[:12]}"

    async def index_document(self, document_id: UUID, scope: KnowledgeScope) -> IndexResult:
        try:
            doc_stmt = select(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id == document_id)
            doc_result = await self.session.execute(doc_stmt)
            doc = doc_result.scalar_one_or_none()
            
            if not doc or doc.status == KnowledgeDocumentStatus.DELETED.value:
                return IndexResult(document_id, "", 0, 0, False, "Document not found or deleted")
                
            markdown = self.storage.read_markdown(doc.id)
            if not markdown:
                return IndexResult(document_id, "", 0, 0, False, "Markdown content not found")
                
            content_hash = hashlib.sha256(markdown.encode('utf-8')).hexdigest()
            if doc.markdown_content_hash == content_hash and doc.active_index_version:
                return IndexResult(document_id, doc.active_index_version, 0, 0, True)
                
            chunker = ParentChildChunker()
            chunks = chunker.chunk(markdown)
            
            parent_count = len(chunks)
            child_count = sum(len(c.child_chunks) for c in chunks)
            
            embed_provider = get_embedding_provider()
            all_child_texts = []
            for c in chunks:
                all_child_texts.extend(c.child_chunks)
                
            embeddings = []
            if all_child_texts:
                embeddings = await embed_provider.embed(all_child_texts)
                
            new_version = self.generate_index_version()
            
            db_chunks = []
            emb_idx = 0
            child_index = 0  # 子块用全局递增序号，避免 (document_id, chunk_type, chunk_index) 不唯一
            for i, p_chunk in enumerate(chunks):
                p_model = KnowledgeChunkModel(
                    id=uuid.uuid4(),
                    document_id=document_id,
                    workspace_id=doc.workspace_id,
                    owner_id=doc.owner_id,
                    index_version=new_version,
                    chunk_type=ChunkType.PARENT.value,
                    content=p_chunk.parent_content,
                    chunk_index=i,
                    heading_path=p_chunk.heading_path or None,
                    token_count=estimate_tokens(p_chunk.parent_content),
                    embedding=None
                )
                db_chunks.append(p_model)

                for c_content in p_chunk.child_chunks:
                    c_model = KnowledgeChunkModel(
                        id=uuid.uuid4(),
                        document_id=document_id,
                        workspace_id=doc.workspace_id,
                        owner_id=doc.owner_id,
                        index_version=new_version,
                        chunk_type=ChunkType.CHILD.value,
                        content=c_content,
                        chunk_index=child_index,
                        heading_path=p_chunk.heading_path or None,
                        parent_chunk_id=p_model.id,
                        token_count=estimate_tokens(c_content),
                        embedding=embeddings[emb_idx]
                    )
                    db_chunks.append(c_model)
                    emb_idx += 1
                    child_index += 1
            
            self.session.add_all(db_chunks)
            
            doc.active_index_version = new_version
            doc.status = KnowledgeDocumentStatus.AVAILABLE.value
            doc.markdown_content_hash = content_hash
            
            now = datetime.now(timezone.utc)
            await self.session.execute(
                update(KnowledgeChunkModel)
                .where(KnowledgeChunkModel.document_id == document_id)
                .where(KnowledgeChunkModel.index_version != new_version)
                .where(KnowledgeChunkModel.deleted_at.is_(None))
                .values(deleted_at=now)
            )
            
            await self.session.commit()
            return IndexResult(document_id, new_version, parent_count, child_count, True)
            
        except Exception as e:
            logger.exception(f"Error indexing document {document_id}: {e}")
            await self.session.rollback()
            try:
                fail_stmt = update(KnowledgeDocumentModel).where(
                    KnowledgeDocumentModel.id == document_id
                ).values(status=KnowledgeDocumentStatus.FAILED.value)
                await self.session.execute(fail_stmt)
                await self.session.commit()
            except Exception as inner_e:
                logger.error(f"Failed to update document status to FAILED: {inner_e}")
                
            return IndexResult(document_id, "", 0, 0, False, str(e))
