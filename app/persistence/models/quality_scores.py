"""QualityScore 持久化模型；对应反思循环每次自评的 5 维分数与修正指令。

字段遵循 spec 4.4 评分协议：
- overall_score：综合评分 0~1
- dimensions JSONB：relevance/information_density/readability/logic_coherence/word_count_compliance
- iteration：1-3，硬性上限
- weakness_summary / refinement_instruction：LLM 输出的修正方向（可空）
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .. import Base


class QualityScoreModel(Base):
    """一次反思自评的完整评分记录；一次 AI 操作可能产生多条（多轮迭代）。"""

    __tablename__ = "quality_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 关联 AI 操作（同一生成任务的多轮自评共享 ai_operation_id）
    ai_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_operations.id", ondelete="SET NULL"), nullable=True
    )
    # 评估的文档
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_documents.id", ondelete="CASCADE"), nullable=False
    )
    # 该评分针对的具体 AnswerVersion（首次生成的版本或某一轮修正版本）
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_versions.id", ondelete="SET NULL"), nullable=True
    )
    # 迭代轮次，1=首次自评，2/3 后续轮，硬性上限 3
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    # 综合评分 0~1，< 0.75 触发修正
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    # 五维细分 scores：{"relevance": 0.85, "information_density": 0.60, ...}
    dimensions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # LLM 输出的弱点总结
    weakness_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LLM 输出的定向修正指令，None 表示综合评分已达标无需修正
    refinement_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 标记本轮反思是否已收敛（达到 0.75 阈值或达到 3 轮上限强制结束）
    converged: Mapped[bool] = mapped_column(
        String(20), nullable=False, default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # 查询某文档全部自评记录的常用入口
        Index("ix_quality_scores_document_iteration", "document_id", "iteration"),
        Index("ix_quality_scores_ai_operation_id", "ai_operation_id"),
    )