import pytest
from app.services.rag.retrieval_service import (
    SearchHit,
    compute_rrf,
    evaluate_evidence_threshold,
)


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
