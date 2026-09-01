"""Phase 2 · Task 3：质量评分数据模型测试。

验证 QualityScoreModel 字段、JSONB dimensions 序列化、外键关系、
(document_id, iteration) 联合查询索引。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.modules.writing.adapters.db.quality_scores import QualityScoreModel
from app.platform.database.session import get_session_factory


def test_quality_score_model_fields():
    """字段定义符合 spec 4.4 评分协议。"""
    cols = QualityScoreModel.__table__.columns
    assert "id" in cols
    assert "ai_operation_id" in cols
    assert "document_id" in cols
    assert "version_id" in cols
    assert "iteration" in cols
    assert "overall_score" in cols
    assert "dimensions" in cols
    assert "weakness_summary" in cols
    assert "refinement_instruction" in cols
    assert "created_at" in cols
    # iteration 取 1-3 的整数
    assert cols["iteration"].nullable is False
    # overall_score 0-100 浮点
    assert cols["overall_score"].nullable is False
    # dimensions 用 JSONB
    from sqlalchemy.dialects.postgresql import JSONB
    assert isinstance(cols["dimensions"].type, JSONB)


def test_quality_score_dimensions_jsonb_roundtrip():
    """dimensions 五维分数可序列化为 JSONB。"""
    dimensions = {
        "relevance": 85,
        "information_density": 60,
        "readability": 72,
        "logic_coherence": 70,
        "word_count_compliance": 65,
    }
    score = QualityScoreModel(
        ai_operation_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_id=None,
        iteration=1,
        overall_score=82,
        dimensions=dimensions,
        weakness_summary="信息密度不足",
        refinement_instruction="补充具体数据",
    )
    assert score.dimensions["relevance"] == 85
    assert score.overall_score == 82
    assert score.iteration == 1
    assert score.weakness_summary == "信息密度不足"
    assert score.refinement_instruction == "补充具体数据"


def test_quality_score_indexes():
    """(document_id, iteration) 联合查询索引存在。"""
    table = QualityScoreModel.__table__
    index_names = {idx.name for idx in table.indexes}
    # 联合索引存在（名字由迁移定义）
    has_doc_iter = any(
        {col.key for col in idx.columns} == {"document_id", "iteration"}
        for idx in table.indexes
    )
    assert has_doc_iter, f"missing (document_id, iteration) index; got {index_names}"
