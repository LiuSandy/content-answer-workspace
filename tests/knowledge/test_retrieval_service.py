from __future__ import annotations

import pytest

from app.modules.knowledge.application import retrieval_service
from app.modules.knowledge.application.retrieval_service import (
    SearchHit,
    compute_rrf,
    evaluate_evidence_threshold,
)
from app.modules.knowledge.ports import RerankerNotConfiguredError


def test_evaluate_evidence_threshold():
    assert evaluate_evidence_threshold([0.85, 0.4], threshold=0.55) is True
    assert evaluate_evidence_threshold([0.4, 0.3], threshold=0.55) is False
    assert evaluate_evidence_threshold([], threshold=0.55) is False


def test_compute_rrf_vector_only():
    # BM25 为空时（如 embedding 正常但全文无命中），RRF 应只依赖向量结果
    vector_hits = [
        SearchHit(chunk_id="chunk_vec_1", doc_id="doc_a", content="c", score=0.9, source="vector"),
    ]
    fused = compute_rrf([], vector_hits)
    assert len(fused) == 1
    assert fused[0]["chunk_id"] == "chunk_vec_1"
    assert fused[0]["source"] == "vector"


class _FakeReranker:
    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [0.91, 0.42, 0.68]


@pytest.mark.asyncio
async def test_rerank_filters_candidates_below_evidence_threshold():
    service = retrieval_service.KnowledgeRetrievalService(
        session=None,
        reranker=_FakeReranker(),
    )
    candidates = [
        {"content": "strong", "rrf_score": 0.02},
        {"content": "weak", "rrf_score": 0.019},
        {"content": "medium", "rrf_score": 0.018},
    ]

    has_evidence, notes = await service._rerank_or_fallback(
        "query", candidates, threshold=0.55, mode="normal"
    )

    assert has_evidence is True
    assert notes == []
    assert [item["content"] for item in candidates] == ["strong", "medium"]


@pytest.mark.asyncio
async def test_rerank_unavailable_does_not_treat_recall_as_evidence(monkeypatch):
    service = retrieval_service.KnowledgeRetrievalService(session=None)

    def unavailable():
        raise RerankerNotConfiguredError("missing reranker")

    monkeypatch.setattr(retrieval_service, "get_reranker_provider", unavailable)
    candidates = [{"content": "weak", "rrf_score": 0.02}]

    has_evidence, notes = await service._rerank_or_fallback(
        "query", candidates, threshold=0.55, mode="normal"
    )

    assert has_evidence is False
    assert notes == ["reranker_not_configured"]
    assert candidates == []


def test_retrieval_candidates_are_deduplicated_by_parent_chunk():
    candidates = [
        {"doc_id": "doc-1", "parent_chunk_id": "parent-1", "chunk_id": "child-1"},
        {"doc_id": "doc-1", "parent_chunk_id": "parent-1", "chunk_id": "child-2"},
        {"doc_id": "doc-1", "parent_chunk_id": "parent-2", "chunk_id": "child-3"},
    ]

    result = retrieval_service.deduplicate_retrieval_candidates(candidates)

    assert result == [candidates[0], candidates[2]]
