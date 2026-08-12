from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .retrieval_dataset import RetrievalEvaluationCase, load_retrieval_dataset
from .retrieval_metrics import citation_accuracy, ndcg_at_k, recall_at_k, reciprocal_rank, refusal_accuracy


@dataclass(frozen=True)
class EvaluationPrediction:
    retrieved_document_ids: list[str]
    cited_document_ids: list[str]
    refused: bool
    fallback: bool
    latency_ms: float


class EvaluationBackend(Protocol):
    def predict(self, case: RetrievalEvaluationCase) -> EvaluationPrediction: ...


class DeterministicBackend:
    """CI backend exercising aggregation without network or private documents."""

    def predict(self, case: RetrievalEvaluationCase) -> EvaluationPrediction:
        started = time.perf_counter()
        retrieved = list(case.relevant_document_ids)
        if retrieved:
            retrieved.append(f"noise-{case.domain}")
        refused = case.expected_mode == "strict" and not retrieved
        fallback = case.expected_mode == "normal" and not retrieved
        return EvaluationPrediction(
            retrieved_document_ids=retrieved,
            cited_document_ids=list(case.expected_citation_document_ids) if retrieved else [],
            refused=refused,
            fallback=fallback,
            latency_ms=(time.perf_counter() - started) * 1000,
        )


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    sample_count: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    citation_accuracy: float
    strict_refusal_accuracy: float
    normal_fallback_accuracy: float
    latency_p50_ms: float
    latency_p95_ms: float


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 1.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def evaluate_cases(cases: list[RetrievalEvaluationCase], backend: EvaluationBackend) -> RetrievalEvaluationResult:
    predictions = [backend.predict(case) for case in cases]
    answerable = [(case, prediction) for case, prediction in zip(cases, predictions) if case.relevant_document_ids]
    strict = [(case, prediction) for case, prediction in zip(cases, predictions) if case.expected_mode == "strict" and not case.relevant_document_ids]
    normal_empty = [(case, prediction) for case, prediction in zip(cases, predictions) if case.expected_mode == "normal" and not case.relevant_document_ids]
    return RetrievalEvaluationResult(
        sample_count=len(cases),
        recall_at_5=_mean([recall_at_k(p.retrieved_document_ids, set(c.relevant_document_ids), 5) for c, p in answerable]),
        recall_at_10=_mean([recall_at_k(p.retrieved_document_ids, set(c.relevant_document_ids), 10) for c, p in answerable]),
        mrr=_mean([reciprocal_rank(p.retrieved_document_ids, set(c.relevant_document_ids)) for c, p in answerable]),
        ndcg_at_10=_mean([ndcg_at_k(p.retrieved_document_ids, c.relevance_grades, 10) for c, p in answerable]),
        citation_accuracy=_mean([citation_accuracy(p.cited_document_ids, set(c.expected_citation_document_ids)) for c, p in answerable]),
        strict_refusal_accuracy=refusal_accuracy([p.refused for _, p in strict], [True] * len(strict)),
        normal_fallback_accuracy=refusal_accuracy([p.fallback for _, p in normal_empty], [True] * len(normal_empty)),
        latency_p50_ms=_percentile([p.latency_ms for p in predictions], 0.50),
        latency_p95_ms=_percentile([p.latency_ms for p in predictions], 0.95),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--backend", choices=["deterministic"], default="deterministic")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate_cases(load_retrieval_dataset(args.dataset), DeterministicBackend())
    payload = asdict(result)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
