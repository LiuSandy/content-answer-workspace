from __future__ import annotations

import math


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant or k <= 0:
        return 0.0
    hits = set(_unique(retrieved)[:k]) & relevant
    return len(hits) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    for rank, document_id in enumerate(_unique(retrieved), 1):
        if document_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: list[str], relevance: dict[str, int], k: int) -> float:
    if not relevance or k <= 0:
        return 0.0

    def dcg(grades: list[int]) -> float:
        return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1))

    actual = [relevance.get(item, 0) for item in _unique(retrieved)[:k]]
    ideal = sorted((grade for grade in relevance.values() if grade > 0), reverse=True)[:k]
    denominator = dcg(ideal)
    return dcg(actual) / denominator if denominator else 0.0


def citation_accuracy(cited: list[str], allowed: set[str]) -> float:
    unique_citations = _unique(cited)
    if not unique_citations:
        return 1.0
    return sum(item in allowed for item in unique_citations) / len(unique_citations)


def refusal_accuracy(predictions: list[bool], expected: list[bool]) -> float:
    if len(predictions) != len(expected):
        raise ValueError("prediction and expectation counts must match")
    if not expected:
        return 1.0
    return sum(prediction == target for prediction, target in zip(predictions, expected)) / len(expected)
