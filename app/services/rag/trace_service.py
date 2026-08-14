from typing import Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models.knowledge import RetrievalTraceModel, RetrievalHitModel

class TraceService:
    SENSITIVE_KEYS = {"api_key", "authorization", "token", "password", "secret", "cookie"}

    def __init__(self, session: AsyncSession):
        self.session = session

    def sanitize_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        cleaned = {}
        for key, value in filters.items():
            if key.lower() in self.SENSITIVE_KEYS:
                cleaned[key] = "[REDACTED]"
            elif isinstance(value, dict):
                cleaned[key] = self.sanitize_filters(value)
            else:
                cleaned[key] = value
        return cleaned

    async def create_trace(self, workspace_id: str, owner_id: str, original_query: str, 
                           rag_decision: bool, decision_reason: str, mode: str, 
                           chat_id: Optional[str] = None, ai_operation_id: Optional[str] = None, 
                           filters: Optional[dict] = None) -> RetrievalTraceModel:
        trace = RetrievalTraceModel(
            workspace_id=workspace_id,
            owner_id=owner_id,
            chat_id=chat_id,
            ai_operation_id=ai_operation_id,
            original_query=original_query,
            rag_decision=rag_decision,
            decision_reason=decision_reason,
            mode=mode,
            filters=self.sanitize_filters(filters) if filters else {}
        )
        self.session.add(trace)
        await self.session.commit()
        return trace

    async def record_hits(self, trace_id: UUID, hits: list[dict]) -> None:
        hit_models = []
        for hit in hits:
            model = RetrievalHitModel(
                trace_id=trace_id,
                chunk_id=hit.get('chunk_id'),
                retrieval_source=hit.get('retrieval_source', 'unknown'),
                rank=hit.get('rank', 0),
                bm25_score=hit.get('bm25_score'),
                vector_score=hit.get('vector_score'),
                rrf_score=hit.get('rrf_score'),
                rerank_score=hit.get('rerank_score'),
                included_in_context=hit.get('included_in_context', False),
                citation_label=hit.get('citation_label'),
                context_snapshot=hit.get('context_snapshot')
            )
            hit_models.append(model)
        self.session.add_all(hit_models)
        await self.session.commit()

    async def finalize_trace(self, trace_id: UUID, latency_ms: int, 
                             fallback_reason: str | None = None, 
                             rewritten_query: str | None = None, 
                             index_version: str | None = None, 
                             embedding_model: str | None = None, 
                             reranker_model: str | None = None) -> None:
        stmt = select(RetrievalTraceModel).where(RetrievalTraceModel.id == trace_id)
        trace = (await self.session.execute(stmt)).scalar_one_or_none()
        if trace:
            trace.latency_ms = latency_ms
            trace.fallback_reason = fallback_reason
            trace.rewritten_query = rewritten_query
            trace.index_version = index_version
            trace.embedding_model = embedding_model
            trace.reranker_model = reranker_model
            await self.session.commit()

    async def get_trace(self, trace_id: UUID, workspace_id: str) -> RetrievalTraceModel | None:
        # 预加载 hits：异步 SQLAlchemy 下惰性访问关系会触发 MissingGreenlet
        stmt = (
            select(RetrievalTraceModel)
            .options(selectinload(RetrievalTraceModel.hits))
            .where(
                RetrievalTraceModel.id == trace_id,
                RetrievalTraceModel.workspace_id == workspace_id
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
