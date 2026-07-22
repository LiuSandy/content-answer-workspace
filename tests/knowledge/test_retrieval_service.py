import pytest
from app.application.knowledge.retrieval_service import evaluate_evidence_threshold


def test_evaluate_evidence_threshold():
    # 最高分为 0.85 >= 0.55，判定证据充分
    assert evaluate_evidence_threshold([0.85, 0.4], threshold=0.55) is True

    # 最高分为 0.4 < 0.55，判定证据不足
    assert evaluate_evidence_threshold([0.4, 0.3], threshold=0.55) is False

    # 空命中列表，判定证据不足
    assert evaluate_evidence_threshold([], threshold=0.55) is False
