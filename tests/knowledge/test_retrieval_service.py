import pytest
from app.application.knowledge.retrieval_service import compute_rrf_scores, evaluate_evidence_threshold, safe_compute_rrf_scores


def test_evaluate_evidence_threshold():
    assert evaluate_evidence_threshold([0.85, 0.4], threshold=0.55) is True
    assert evaluate_evidence_threshold([0.4, 0.3], threshold=0.55) is False
    assert evaluate_evidence_threshold([], threshold=0.55) is False


def test_safe_compute_rrf_scores():
    # 当 BM25 为空或出现异常时，安全降级至仅依赖向量检索
    bm25_ranks = {}
    vector_ranks = {"chunk_vec_1": 1}
    fused = safe_compute_rrf_scores(bm25_ranks, vector_ranks)
    assert len(fused) == 1
    assert fused[0][0] == "chunk_vec_1"
