from typing import Any


def compute_rrf_scores(
    bm25_ranks: dict[str, int], vector_ranks: dict[str, int], k: int = 60
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}

    for chunk_id, rank in bm25_ranks.items():
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))

    for chunk_id, rank in vector_ranks.items():
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))

    sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


def evaluate_evidence_threshold(scores: list[float], threshold: float = 0.55) -> bool:
    if not scores:
        return False
    return max(scores) >= threshold
