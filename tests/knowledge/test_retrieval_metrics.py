import json

import pytest

from app.evaluation.retrieval_dataset import load_retrieval_dataset
from app.evaluation.retrieval_metrics import (
    citation_accuracy,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    refusal_accuracy,
)


def test_rank_metrics_cover_hits_misses_and_graded_relevance():
    retrieved = ["noise", "relevant-b", "relevant-a"]
    relevant = {"relevant-a", "relevant-b"}
    assert recall_at_k(retrieved, relevant, 2) == 0.5
    assert reciprocal_rank(retrieved, relevant) == 0.5
    assert ndcg_at_k(retrieved, {"relevant-a": 3, "relevant-b": 1}, 3) == pytest.approx(0.5413403)


def test_metrics_handle_empty_inputs_and_duplicate_retrievals():
    assert recall_at_k([], {"a"}, 5) == 0.0
    assert recall_at_k(["a", "a"], {"a"}, 2) == 1.0
    assert reciprocal_rank([], {"a"}) == 0.0
    assert ndcg_at_k([], {"a": 3}, 5) == 0.0
    assert citation_accuracy([], {"a"}) == 1.0
    assert citation_accuracy(["a", "bad"], {"a"}) == 0.5
    assert refusal_accuracy([True, False], [True, True]) == 0.5


def test_dataset_loader_validates_contract(tmp_path):
    valid = {
        "id": "case-1",
        "domain": "algorithm",
        "question": "q",
        "relevantDocumentIds": ["doc-a"],
        "relevanceGrades": {"doc-a": 3},
        "expectedMode": "strict",
        "expectedRefusal": False,
        "expectedCitationDocumentIds": ["doc-a"],
    }
    path = tmp_path / "eval.jsonl"
    path.write_text(json.dumps(valid) + "\n" + json.dumps(valid), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate evaluation id"):
        load_retrieval_dataset(path)
