from pathlib import Path

from app.evaluation.retrieval_dataset import load_retrieval_dataset
from app.evaluation.run_retrieval_eval import DeterministicBackend, evaluate_cases


DATASET = Path("docs/evaluations/private-knowledge-rag.jsonl")


def test_retrieval_quality_baseline_is_computed_from_dataset():
    cases = load_retrieval_dataset(DATASET)
    assert len(cases) >= 30
    result = evaluate_cases(cases, DeterministicBackend())
    assert result.sample_count == len(cases)
    assert result.recall_at_5 >= 0.80
    assert result.mrr >= 0.70
    assert result.ndcg_at_10 >= 0.75
    assert result.citation_accuracy >= 0.90
    assert result.strict_refusal_accuracy >= 0.90
    assert result.normal_fallback_accuracy >= 0.90
