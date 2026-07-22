from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

@dataclass
class SearchHit:
    chunk_id: str
    doc_id: str
    content: str
    score: float
    source: str  # "bm25" or "vector"

def compute_rrf(bm25_hits: List[SearchHit], vector_hits: List[SearchHit], k: int = 60) -> List[Dict[str, Any]]:
    rrf_scores: Dict[str, float] = {}
    hit_map: Dict[str, SearchHit] = {}

    for rank, hit in enumerate(bm25_hits, start=1):
        rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + (1.0 / (k + rank))
        hit_map[hit.chunk_id] = hit

    for rank, hit in enumerate(vector_hits, start=1):
        rrf_scores[hit.chunk_id] = rrf_scores.get(hit.chunk_id, 0.0) + (1.0 / (k + rank))
        hit_map[hit.chunk_id] = hit

    sorted_chunks = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)

    fused_results = []
    for chunk_id, rrf_score in sorted_chunks:
        hit = hit_map[chunk_id]
        fused_results.append({
            "chunk_id": chunk_id,
            "doc_id": hit.doc_id,
            "content": hit.content,
            "rrf_score": rrf_score,
        })
    return fused_results

def compute_rrf_scores(bm25_ranks: Dict[str, int], vector_ranks: Dict[str, int], k: int = 60) -> List[Tuple[str, float]]:
    scores: Dict[str, float] = {}
    for chunk_id, rank in bm25_ranks.items():
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
    for chunk_id, rank in vector_ranks.items():
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

def safe_compute_rrf_scores(bm25_ranks: Dict[str, int], vector_ranks: Dict[str, int], k: int = 60) -> List[Tuple[str, float]]:
    try:
        return compute_rrf_scores(bm25_ranks, vector_ranks, k=k)
    except Exception:
        scores = {chunk_id: 1.0 / (k + rank) for chunk_id, rank in vector_ranks.items()}
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

def evaluate_evidence_threshold(scores: List[float], threshold: float = 0.55) -> bool:
    if not scores:
        return False
    return any(score >= threshold for score in scores)
