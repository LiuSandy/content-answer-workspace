import json
from pathlib import Path
import pytest


def test_evaluations_jsonl_validity():
    eval_path = Path("docs/evaluations/private-knowledge-rag.jsonl")
    assert eval_path.exists()
    lines = eval_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3

    for line in lines:
        sample = json.loads(line)
        assert "id" in sample
        assert "domain" in sample
        assert "question" in sample
        assert "expected_mode" in sample
