import pytest
from app.application.knowledge.retrieval_service import compute_rrf_scores


def test_compute_rrf_scores():
    bm25_ranks = {"chunk_1": 1, "chunk_2": 2}
    vector_ranks = {"chunk_2": 1, "chunk_3": 2}

    fused = compute_rrf_scores(bm25_ranks, vector_ranks, k=60)
    assert len(fused) == 3
    # chunk_2 同时在两路中出现，得分最高
    assert fused[0][0] == "chunk_2"
    assert fused[0][1] > fused[1][1]
