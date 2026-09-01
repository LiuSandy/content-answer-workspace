from __future__ import annotations
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.modules.knowledge.domain.models import KnowledgeDocumentStatus, ChunkType, KnowledgeScope
from app.modules.knowledge.adapters.db.models import KnowledgeDocumentModel, KnowledgeChunkModel
from app.modules.knowledge.application.chunking import ParentChildChunker
from app.modules.knowledge.application.context_builder import estimate_tokens
from app.modules.knowledge.ports import EmbeddingPort
from app.modules.knowledge.adapters.db.storage import KnowledgeStorage
from app.modules.knowledge.adapters.embeddings import get_embedding_adapter
from app.platform.config.runtime import get_knowledge_settings

logger = logging.getLogger(__name__)


def get_embedding_provider() -> EmbeddingPort:
    return get_embedding_adapter()


@dataclass
class IndexResult:
    """一次文档索引操作的结果，供后台索引任务记录和返回。"""

    document_id: UUID
    index_version: str
    parent_count: int
    child_count: int
    success: bool
    error: str | None = None

class IndexingService:
    """将已确认的 Markdown 文档转换为可检索的父子切片和向量索引。"""

    def __init__(
        self,
        session: AsyncSession,
        storage: KnowledgeStorage,
        embedding: EmbeddingPort | None = None,
    ):
        self.session = session
        self.storage = storage
        self._embedding = embedding

    @staticmethod
    def generate_index_version() -> str:
        """生成本次索引的版本号，用于区分新旧切片。"""
        return f"v_{uuid.uuid4().hex[:12]}"

    async def index_document(self, document_id: UUID, scope: KnowledgeScope) -> IndexResult:
        """为一份文档建立完整索引。

        整体流程：读取正式 Markdown → 判断是否需要重建 → 父子分块 →
        为子块生成向量 → 写入新版本切片 → 切换文档到新版本。
        """
        try:
            # 1. 从数据库读取逻辑文档；已删除文档不再允许建立索引。
            doc_stmt = select(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id == document_id)
            doc_result = await self.session.execute(doc_stmt)
            doc = doc_result.scalar_one_or_none()
            
            if not doc or doc.status == KnowledgeDocumentStatus.DELETED.value:
                return IndexResult(document_id, "", 0, 0, False, "Document not found or deleted")
                
            # 2. 只读取正式 Markdown（{document_id}.md），不读取候选稿。
            markdown = self.storage.read_markdown(doc.id)
            if not markdown:
                return IndexResult(document_id, "", 0, 0, False, "Markdown content not found")

            # 3. 通过 Markdown 内容哈希实现幂等：内容没有变化且已有索引时直接复用。
            content_hash = self.storage.compute_file_hash(
                self.storage.markdown_path(doc.id), get_knowledge_settings().source_file_buffer_bytes
            )
            if doc.markdown_content_hash == content_hash and doc.active_index_version:
                return IndexResult(document_id, doc.active_index_version, 0, 0, True)

            # 4. 按标题和段落组织父块，再把父块切成更适合向量检索的子块。
            chunker = ParentChildChunker()
            chunks = chunker.chunk(markdown)

            parent_count = len(chunks)
            child_count = sum(len(c.child_chunks) for c in chunks)

            # 5. 只有子块参与向量化；父块主要用于召回后的上下文扩展。
            embed_provider = self._embedding or get_embedding_provider()
            embedding_batch_size = max(1, get_knowledge_settings().embedding_batch_size)

            # 6. 先生成新的索引版本，后续所有父块和子块都写入这个版本。
            new_version = self.generate_index_version()

            db_chunks = []
            child_index = 0  # 子块用全局递增序号，避免 (document_id, chunk_type, chunk_index) 不唯一
            pending_child_models = []
            pending_child_texts = []

            async def flush_embedding_batch() -> None:
                """向量化当前批次，并把结果按原顺序写回子块模型。"""
                if not pending_child_texts:
                    return
                batch_embeddings = await embed_provider.embed(pending_child_texts)
                if len(batch_embeddings) != len(pending_child_models):
                    raise ValueError(
                        "Embedding result count does not match child chunk count"
                    )
                for child_model, embedding in zip(pending_child_models, batch_embeddings):
                    child_model.embedding = embedding
                pending_child_models.clear()
                pending_child_texts.clear()

            # 7. 构造待写入的数据库切片对象。
            #    每个父块不保存 embedding；每个子块关联父块并保存对应 embedding。
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
                        embedding=None,
                    )
                    db_chunks.append(c_model)
                    pending_child_models.append(c_model)
                    pending_child_texts.append(c_content)
                    child_index += 1
                    # 达到批量大小后立即调用 Embedding，避免积累全部子块文本。
                    if len(pending_child_texts) >= embedding_batch_size:
                        await flush_embedding_batch()

            # 处理最后一个不足批量大小的尾批次。
            await flush_embedding_batch()

            # 8. 批量写入新版本切片，减少数据库交互次数。
            self.session.add_all(db_chunks)

            # 9. 原子地将文档指向新索引版本，并标记为可用。
            #    在事务提交前，旧版本仍然保留，避免重建索引期间没有可用数据。
            doc.active_index_version = new_version
            doc.status = KnowledgeDocumentStatus.AVAILABLE.value
            doc.markdown_content_hash = content_hash

            # 10. 新版本成功写入后，旧版本切片采用软删除，而不是物理删除。
            now = datetime.now(timezone.utc)
            await self.session.execute(
                update(KnowledgeChunkModel)
                .where(KnowledgeChunkModel.document_id == document_id)
                .where(KnowledgeChunkModel.index_version != new_version)
                .where(KnowledgeChunkModel.deleted_at.is_(None))
                .values(deleted_at=now)
            )

            # 11. 提交整个索引事务：切片、文档状态和旧版本清理一起生效。
            await self.session.commit()
            return IndexResult(document_id, new_version, parent_count, child_count, True)

        except Exception as e:
            # 任意阶段失败都回滚当前事务，并将文档标记为 FAILED，避免留下半套索引。
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
