"""知识库批量重索引脚本。

用途：分块策略 / tokenizer / embedding 配置变更后，把存量文档迁移到新索引
（新分块、heading_path、真实向量）。IndexingService 有内容 hash 短路逻辑，
内容未变的文档不会自动重建，因此这里先清空 active_index_version 强制重建。

用法：
    uv run python scripts/reindex_knowledge.py --dry-run   # 只列出将要重索引的文档
    uv run python scripts/reindex_knowledge.py             # 执行重索引
    uv run python scripts/reindex_knowledge.py --workspace default  # 限定工作区
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.config import get_knowledge_settings, load_env_file
from app.domain.knowledge import KnowledgeDocumentStatus, KnowledgeScope
from app.persistence.models.knowledge import KnowledgeDocumentModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("reindex_knowledge")

# 只有已发布 Markdown 的文档才可重索引；AWAITING_CONFIRMATION 尚无正式稿
_REINDEXABLE_STATUSES = (
    KnowledgeDocumentStatus.AVAILABLE.value,
    KnowledgeDocumentStatus.INDEXING.value,
    KnowledgeDocumentStatus.FAILED.value,
)


async def _list_target_documents(session, workspace_id: str | None) -> list[KnowledgeDocumentModel]:
    """列出待重索引的文档：非删除、状态可重索引、已有正式 Markdown。"""
    stmt = select(KnowledgeDocumentModel).where(
        KnowledgeDocumentModel.status.in_(_REINDEXABLE_STATUSES),
        KnowledgeDocumentModel.markdown_path.is_not(None),
    )
    if workspace_id:
        stmt = stmt.where(KnowledgeDocumentModel.workspace_id == workspace_id)
    return list((await session.execute(stmt)).scalars().all())


async def run(workspace_id: str | None, dry_run: bool) -> int:
    load_env_file()

    # 先校验 embedding 已配置：未配置时立即失败，
    # 而不是逐个文档报错（禁止用 Mock 向量重建索引）
    from app.infrastructure.knowledge.embedding import get_embedding_provider
    get_embedding_provider()

    from app.persistence.session import get_session_factory
    from app.application.knowledge.indexing_service import IndexingService
    from app.infrastructure.knowledge.storage import KnowledgeStorage

    settings = get_knowledge_settings()
    storage = KnowledgeStorage(settings.sources_dir, settings.documents_dir)
    factory = get_session_factory()

    async with factory() as session:
        docs = await _list_target_documents(session, workspace_id)

    if not docs:
        logger.info("没有需要重索引的文档")
        return 0

    logger.info("待重索引文档 %d 篇：", len(docs))
    for doc in docs:
        logger.info("  [%s] %s (status=%s, index=%s)", doc.workspace_id, doc.title, doc.status, doc.active_index_version)

    if dry_run:
        logger.info("dry-run 模式，未做任何修改")
        return 0

    succeeded = 0
    failed: list[tuple[str, str]] = []
    for doc in docs:
        # 每篇文档独立 session：单篇失败不影响其余文档
        async with factory() as session:
            target = await session.get(KnowledgeDocumentModel, doc.id)
            if target is None:
                continue
            # 清空 active_index_version 绕过内容 hash 短路，强制重建
            target.active_index_version = None
            await session.commit()

            svc = IndexingService(session, storage)
            scope = KnowledgeScope(workspace_id=target.workspace_id, owner_id=target.owner_id)
            result = await svc.index_document(target.id, scope)
            if result.success:
                succeeded += 1
                logger.info(
                    "✓ %s → %s (parent=%d, child=%d)",
                    doc.title, result.index_version, result.parent_count, result.child_count,
                )
            else:
                failed.append((doc.title, result.error or "unknown"))
                logger.error("✗ %s: %s", doc.title, result.error)

    logger.info("重索引完成：成功 %d / 失败 %d", succeeded, len(failed))
    if failed:
        logger.error("失败清单：")
        for title, err in failed:
            logger.error("  %s: %s", title, err)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="知识库批量重索引")
    parser.add_argument("--workspace", default=None, help="仅重索引指定 workspace 的文档")
    parser.add_argument("--dry-run", action="store_true", help="只列出将要重索引的文档，不执行")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.workspace, args.dry_run)))


if __name__ == "__main__":
    main()
