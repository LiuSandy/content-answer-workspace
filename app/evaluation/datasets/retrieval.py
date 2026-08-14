from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    id: str
    domain: str
    question: str
    relevant_document_ids: tuple[str, ...]
    relevance_grades: dict[str, int]
    expected_mode: str
    expected_refusal: bool
    expected_citation_document_ids: tuple[str, ...]


def load_retrieval_dataset(path: str | Path) -> list[RetrievalEvaluationCase]:
    cases: list[RetrievalEvaluationCase] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON on line {line_number}: {error}") from error
        required = {
            "id", "domain", "question", "relevantDocumentIds", "relevanceGrades",
            "expectedMode", "expectedRefusal", "expectedCitationDocumentIds",
        }
        missing = required - item.keys()
        if missing:
            raise ValueError(f"line {line_number} missing fields: {sorted(missing)}")
        case_id = str(item["id"]).strip()
        if case_id in seen:
            raise ValueError(f"duplicate evaluation id: {case_id}")
        seen.add(case_id)
        if item["expectedMode"] not in {"normal", "strict"}:
            raise ValueError(f"invalid expectedMode for {case_id}")
        grades = item["relevanceGrades"]
        if not isinstance(grades, dict) or any(
            isinstance(grade, bool) or not isinstance(grade, int) or grade < 0
            for grade in grades.values()
        ):
            raise ValueError(f"invalid relevanceGrades for {case_id}")
        relevant = tuple(dict.fromkeys(item["relevantDocumentIds"]))
        if item["expectedMode"] == "strict" and not item["expectedRefusal"] and not relevant:
            raise ValueError(f"strict non-refusal case {case_id} requires relevant documents")
        cases.append(RetrievalEvaluationCase(
            id=case_id,
            domain=str(item["domain"]),
            question=str(item["question"]),
            relevant_document_ids=relevant,
            relevance_grades={str(key): value for key, value in grades.items()},
            expected_mode=item["expectedMode"],
            expected_refusal=bool(item["expectedRefusal"]),
            expected_citation_document_ids=tuple(dict.fromkeys(item["expectedCitationDocumentIds"])),
        ))
    return cases
