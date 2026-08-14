import pytest
from app.services.rag.retrieval_service import SearchHit, compute_rrf

def test_compute_rrf():
    bm25_hits = [
        SearchHit(chunk_id="chunk_1", doc_id="doc_a", content="content 1", score=10.0, source="bm25"),
        SearchHit(chunk_id="chunk_2", doc_id="doc_a", content="content 2", score=5.0, source="bm25"),
    ]
    vector_hits = [
        SearchHit(chunk_id="chunk_2", doc_id="doc_a", content="content 2", score=0.9, source="vector"),
        SearchHit(chunk_id="chunk_3", doc_id="doc_b", content="content 3", score=0.8, source="vector"),
    ]

    fused = compute_rrf(bm25_hits, vector_hits, k=60)
    assert len(fused) == 3
    # chunk_2 同时在 bm25 和 vector 中出现，它的 RRF 分数应该最高
    assert fused[0]["chunk_id"] == "chunk_2"
