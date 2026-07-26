"""知识库混合检索服务：BM25 + 向量召回 → RRF 融合 → rerank → 上下文组装。

单独成模块是为了让 Agent 节点与 API 路由共享同一条检索链路，
避免两处各自实现召回/融合/证据判定逻辑。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.domain.knowledge import KnowledgeScope
from app.core.config import get_knowledge_settings
from app.domain.dto import LLMRequest
from app.infrastructure.knowledge.embedding import (
    get_embedding_provider,
    EmbeddingNotConfiguredError,
)
from app.infrastructure.knowledge.reranker import (
    get_reranker_provider,
    RerankerNotConfiguredError,
)
from app.infrastructure.llm.registry import llm_provider_registry
from app.prompts.registry import prompt_registry
from app.application.knowledge.context_builder import ContextBuilder, ContextBlock
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    """单路召回命中项；统一 BM25 与向量两路的返回结构，便于 RRF 融合。"""

    chunk_id: str
    doc_id: str
    content: str
    score: float
    source: str
    parent_chunk_id: str | None = None
    heading_path: str = ""


def compute_rrf(bm25_hits: List[SearchHit], vector_hits: List[SearchHit], k: int = 60) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion：融合两路召回的排名，输出带完整评分明细的列表。

    是检索链路唯一的 RRF 实现——评分明细（bm25/vector/rrf）需要透传给
    trace 记录，所以返回 dict 而非仅排序结果。
    """
    rrf_scores: Dict[str, float] = {}
    hit_map: Dict[str, SearchHit] = {}
    bm25_score_map: Dict[str, float] = {}
    vector_score_map: Dict[str, float] = {}
    sources_map: Dict[str, list[str]] = {}

    for rank, hit in enumerate(bm25_hits, start=1):
        rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + (1.0 / (k + rank))
        hit_map[hit.chunk_id] = hit
        bm25_score_map[hit.chunk_id] = hit.score
        sources_map.setdefault(hit.chunk_id, []).append("bm25")

    for rank, hit in enumerate(vector_hits, start=1):
        rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + (1.0 / (k + rank))
        hit_map[hit.chunk_id] = hit
        vector_score_map[hit.chunk_id] = hit.score
        sources_map.setdefault(hit.chunk_id, []).append("vector")

    sorted_chunks = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)

    fused_results = []
    for rank, (chunk_id, rrf_score) in enumerate(sorted_chunks, start=1):
        hit = hit_map[chunk_id]
        src_list = sources_map.get(chunk_id, ["hybrid"])
        source_str = "hybrid" if len(src_list) > 1 else src_list[0]
        fused_results.append({
            "chunk_id": chunk_id,
            "doc_id": hit.doc_id,
            "content": hit.content,
            "rrf_score": rrf_score,
            "rrf_rank": rank,
            "bm25_score": bm25_score_map.get(chunk_id, 0.0),
            "vector_score": vector_score_map.get(chunk_id, 0.0),
            "source": source_str,
            "heading_path": hit.heading_path,
            "parent_chunk_id": hit.parent_chunk_id
        })
    return fused_results


def _sanitize_bm25_query(query: str) -> str:
    """清洗 pg_search 查询语法保留字符（: ( ) [ ] 等），只保留普通检索词。

    单独抽出是因为用户输入直接进入 @@@ 查询解析器，
    语法字符会导致整条 SQL 报错而非返回空结果。
    """
    cleaned = re.sub(r'[:^~*?!\\"\'()\[\]{}<>+-]', " ", query)
    return " ".join(cleaned.split())


def evaluate_evidence_threshold(scores: List[float], threshold: float = 0.55) -> bool:
    """判断 rerank 分数是否达到证据阈值；只接受 [0,1] 量纲的 rerank 分数。

    单独抽出是因为 strict 模式的拒答决策依赖它，必须保证阈值语义只有一处。
    """
    if not scores:
        return False
    return any(score >= threshold for score in scores)


@dataclass
class RetrievalRequest:
    query: str
    scope: KnowledgeScope
    mode: str = "normal"
    top_k_bm25: int = 20
    top_k_vector: int = 20
    reranker_top_k: int = 8
    evidence_threshold: float = 0.55
    context_token_budget: int = 6000


@dataclass
class RetrievalResult:
    has_evidence: bool
    context_text: str
    sources: list[dict]
    trace_hits: list[dict]
    rewritten_query: str
    index_version: str | None = None
    fallback_reason: str | None = None
    # 检索链路的降级说明（如向量/rerank 不可用），供 trace 与前端展示
    degradation_notes: list[str] = field(default_factory=list)


class KnowledgeRetrievalService:
    """执行一次完整的混合检索请求；持有 DB 会话，不持有全局状态。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _rewrite_query(self, query: str) -> str:
        """用对话 LLM 改写查询以提升召回；失败时安全回退到原始查询。

        复用 prompt_registry + llm_provider_registry，而不是挪用
        embedding/reranker 的凭据和模型（它们面向的端点未必支持 chat）。
        """
        try:
            rendered = prompt_registry.render("knowledge.query_rewrite", query=query)
            provider = llm_provider_registry.get("deepseek")
            request = LLMRequest(
                messages=rendered.messages,
                model=rendered.model,
                temperature=rendered.temperature,
                max_tokens=rendered.max_tokens,
            )
            response = await provider.generate(request)
            rewritten = response.content.strip()
            return rewritten or query
        except Exception as e:
            logger.warning(f"Query rewrite skipped/failed: {e}")
            return query

    async def _search_bm25(self, query: str, scope: KnowledgeScope, limit: int) -> list[SearchHit]:
        """BM25 全文召回；走 ParadeDB pg_search 的 bm25 索引。

        计划明确禁止用 ts_rank_cd 静默替代（'simple' 分词对中文完全失效）。
        查询词先清洗掉 pg_search 查询语法字符，避免用户输入触发解析错误。
        """
        sanitized = _sanitize_bm25_query(query)
        if not sanitized:
            return []
        hits: list[SearchHit] = []
        bm25_sql = text("""
            SELECT id::text, content, document_id::text, heading_path, parent_chunk_id::text,
                   paradedb.score(id) AS score
            FROM knowledge_chunks
            WHERE content @@@ :query
              AND chunk_type = 'child'
              AND deleted_at IS NULL
              AND workspace_id = :workspace_id
              AND owner_id = :owner_id
            ORDER BY score DESC
            LIMIT :limit
        """)
        result = await self.session.execute(bm25_sql, {
            "query": sanitized,
            "workspace_id": scope.workspace_id,
            "owner_id": scope.owner_id,
            "limit": limit
        })
        for row in result:
            hits.append(SearchHit(
                row.id, row.document_id, row.content, row.score, "bm25",
                row.parent_chunk_id, row.heading_path or ""
            ))
        return hits

    async def _search_vector(self, query_vec: list[float], scope: KnowledgeScope, limit: int) -> list[SearchHit]:
        """向量相似度召回。"""
        hits: list[SearchHit] = []
        vec_sql = text("""
            SELECT id::text, content, document_id::text, heading_path, parent_chunk_id::text,
                   1 - (embedding <=> CAST(:query_vec AS vector)) AS score
            FROM knowledge_chunks
            WHERE chunk_type = 'child'
              AND deleted_at IS NULL
              AND embedding IS NOT NULL
              AND workspace_id = :workspace_id
              AND owner_id = :owner_id
            ORDER BY embedding <=> CAST(:query_vec AS vector)
            LIMIT :limit
        """)
        result = await self.session.execute(vec_sql, {
            "query_vec": str(query_vec),
            "workspace_id": scope.workspace_id,
            "owner_id": scope.owner_id,
            "limit": limit
        })
        for row in result:
            hits.append(SearchHit(
                row.id, row.document_id, row.content, row.score, "vector",
                row.parent_chunk_id, row.heading_path or ""
            ))
        return hits

    async def _rerank_or_fallback(
        self, query: str, top_n: list[dict], threshold: float, mode: str
    ) -> tuple[bool, list[str]]:
        """对候选做 rerank 并判定证据；rerank 不可用时走显式降级。

        单独抽出是为了把"量纲对齐"约束集中在一处：证据阈值只允许与
        rerank 分数（[0,1]）比较，绝不与 RRF 分数（~0.016 量级）比较。
        返回 (has_evidence, degradation_notes)，并就地为 top_n 写入 rerank_score。
        """
        notes: list[str] = []
        rerank_scores: list[float] | None = None
        try:
            reranker = get_reranker_provider()
            rerank_scores = await reranker.rerank(query, [item['content'] for item in top_n])
            if len(rerank_scores) != len(top_n):
                logger.error("Rerank 返回数量不匹配: %d != %d", len(rerank_scores), len(top_n))
                rerank_scores = None
        except RerankerNotConfiguredError as e:
            logger.warning("Reranker 未配置: %s", e)
            notes.append("reranker_not_configured")
            rerank_scores = None
        except Exception as e:
            logger.error(f"Rerank failed: {e}")
            notes.append("reranker_error")
            rerank_scores = None

        if rerank_scores is not None:
            for i, item in enumerate(top_n):
                item['rerank_score'] = rerank_scores[i]
            top_n.sort(key=lambda x: x['rerank_score'], reverse=True)
            return evaluate_evidence_threshold(rerank_scores, threshold), notes

        # rerank 不可用：保持 RRF 排序。RRF 分数与阈值量纲不同，
        # 不做阈值判定——normal 模式视"有命中"为有证据；strict 模式因无法
        # 校验阈值而拒绝，语义由调用方 retrieve() 处理。
        for item in top_n:
            item['rerank_score'] = None
        return bool(top_n), notes

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        if request.mode == "off":
            return RetrievalResult(False, "", [], [], request.query, fallback_reason="Retrieval mode is off")

        degradation_notes: list[str] = []
        rewritten_query = await self._rewrite_query(request.query)

        query_vec: list[float] = []
        try:
            embed_provider = get_embedding_provider()
            vecs = await embed_provider.embed([rewritten_query])
            if vecs:
                query_vec = vecs[0]
        except EmbeddingNotConfiguredError as e:
            logger.warning("Embedding 未配置，向量检索不可用: %s", e)
            degradation_notes.append("embedding_not_configured")
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            degradation_notes.append("embedding_error")

        bm25_hits: list[SearchHit] = []
        vector_hits: list[SearchHit] = []

        try:
            bm25_hits = await self._search_bm25(rewritten_query, request.scope, request.top_k_bm25)
        except Exception as e:
            logger.error(f"BM25 failed: {e}")
            degradation_notes.append("bm25_error")

        if query_vec:
            try:
                vector_hits = await self._search_vector(query_vec, request.scope, request.top_k_vector)
            except Exception as e:
                logger.error(f"Vector search failed: {e}")
                degradation_notes.append("vector_error")

        settings = get_knowledge_settings()
        fused = compute_rrf(bm25_hits, vector_hits, k=settings.rrf_k)
        top_n = fused[:request.reranker_top_k]

        if not top_n:
            return RetrievalResult(
                False, "", [], [], rewritten_query,
                fallback_reason="No documents retrieved",
                degradation_notes=degradation_notes,
            )

        has_evidence, rerank_notes = await self._rerank_or_fallback(
            rewritten_query, top_n, request.evidence_threshold, request.mode
        )
        degradation_notes.extend(rerank_notes)
        rerank_unavailable = bool(rerank_notes)

        if request.mode == "strict" and rerank_unavailable:
            # strict 模式承诺"只依据达到阈值的证据作答"；rerank 不可用时
            # 无法校验阈值，显式拒绝而非假装有证据。
            return RetrievalResult(
                False, "", [], [], rewritten_query,
                fallback_reason="Reranker unavailable; cannot verify evidence threshold in strict mode",
                degradation_notes=degradation_notes,
            )

        if request.mode == "strict" and not has_evidence:
            return RetrievalResult(
                False, "", [], [], rewritten_query,
                fallback_reason="No evidence above threshold in strict mode",
                degradation_notes=degradation_notes,
            )

        # 取 parent 上下文
        parent_ids = [item['parent_chunk_id'] for item in top_n if item['parent_chunk_id']]
        parent_map = {}
        if parent_ids:
            try:
                parent_sql = text("""
                    SELECT id::text, content, document_id::text, heading_path
                    FROM knowledge_chunks
                    WHERE id = ANY(:parent_ids)
                      AND chunk_type = 'parent'
                      AND deleted_at IS NULL
                """)
                parent_result = await self.session.execute(parent_sql, {"parent_ids": parent_ids})
                for row in parent_result:
                    parent_map[row.id] = row.content
            except Exception as e:
                logger.error(f"Failed to fetch parent chunks: {e}")

        # 取文档元数据
        doc_ids = list(set([item['doc_id'] for item in top_n]))
        doc_map = {}
        if doc_ids:
            try:
                doc_sql = text("""
                    SELECT id::text, title, source_url, updated_at
                    FROM knowledge_documents
                    WHERE id = ANY(:doc_ids)
                """)
                doc_result = await self.session.execute(doc_sql, {"doc_ids": doc_ids})
                for row in doc_result:
                    doc_map[row.id] = {
                        "title": row.title,
                        "source_url": row.source_url,
                        "updated_at": row.updated_at
                    }
            except Exception as e:
                logger.error(f"Failed to fetch document metadata: {e}")

        # 先组装 block 并交给 ContextBuilder 做预算裁剪，
        # 再按"实际纳入上下文"的结果生成引用标签——标签必须与上下文严格对齐，
        # 否则模型会引用不存在的 [Sx]。
        blocks = []
        contents_to_use: list[str] = []
        for item in top_n:
            parent_content = parent_map.get(item['parent_chunk_id'])
            content_to_use = parent_content if parent_content else item['content']
            contents_to_use.append(content_to_use)
            doc_meta = doc_map.get(item['doc_id'], {})
            blocks.append(ContextBlock(
                doc_title=doc_meta.get('title', 'Unknown Document'),
                content=content_to_use,
                source_type="file",
                source_url=doc_meta.get('source_url'),
                updated_at=str(doc_meta.get('updated_at', '')) if doc_meta.get('updated_at') else None
            ))

        builder = ContextBuilder(max_tokens=request.context_token_budget)
        context_text, included_sources = builder.build_context(blocks)
        included_count = len(included_sources)

        sources = []
        trace_hits = []
        for idx, item in enumerate(top_n):
            content_to_use = contents_to_use[idx]
            doc_meta = doc_map.get(item['doc_id'], {})
            included = idx < included_count
            label = f"[S{idx + 1}]" if included else None

            if included:
                sources.append({
                    "documentId": item['doc_id'],
                    "title": doc_meta.get('title', 'Unknown Document'),
                    "sourceUrl": doc_meta.get('source_url'),
                    "text": content_to_use[:300],
                    "score": item['rerank_score'] if item['rerank_score'] is not None else item['rrf_score'],
                    "label": label
                })

            trace_hits.append({
                "chunk_id": item['chunk_id'],
                "document_id": item['doc_id'],
                "retrieval_source": item['source'],
                "rank": item.get('rrf_rank', 0),
                "bm25_score": item.get('bm25_score', 0.0),
                "vector_score": item.get('vector_score', 0.0),
                "rrf_score": item.get('rrf_score', 0.0),
                "rerank_score": item['rerank_score'],
                "included_in_context": included,
                "citation_label": label,
                "context_snapshot": content_to_use[:200]
            })

        return RetrievalResult(
            has_evidence=has_evidence,
            context_text=context_text,
            sources=sources,
            trace_hits=trace_hits,
            rewritten_query=rewritten_query,
            fallback_reason="; ".join(degradation_notes) if degradation_notes else None,
            degradation_notes=degradation_notes,
        )
