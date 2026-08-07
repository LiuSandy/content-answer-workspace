"""PublishAnalystService：基于发布指标生成结构化分析报告（roadmap R11）。

- 至少 3 个日期的指标记录才生成报告（避免数据不足）。
- 报告可追溯输入快照（metrics_snapshot）。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..persistence.models.publish_metrics import PublishMetricsModel
from ..persistence.models.documents import AnswerDocument

logger = logging.getLogger(__name__)


class PublishAnalystService:
    def __init__(self, session):
        self.session = session

    async def analyze_document(self, document_id) -> dict | None:
        """分析单个文档的发布数据，返回结构化报告或 None（数据不足）。"""
        rows = (
            await self.session.execute(
                select(PublishMetricsModel)
                .where(PublishMetricsModel.document_id == document_id)
                .order_by(PublishMetricsModel.recorded_at)
            )
        ).scalars().all()

        unique_dates = len({r.recorded_at.date() for r in rows if r.recorded_at})
        if unique_dates < 3:
            return None  # 数据不足，不生成伪结论

        doc_result = await self.session.execute(
            select(AnswerDocument)
            .options(selectinload(AnswerDocument.source_item))
            .where(AnswerDocument.id == document_id)
        )
        doc = doc_result.scalar_one_or_none()
        title = doc.source_item.title if doc and doc.source_item else "未知"
        metrics_data = [
            {
                "views": r.views or 0,
                "likes": r.likes or 0,
                "comments": r.comments or 0,
                "collects": r.collects or 0,
                "label": r.label,
                "recordedAt": r.recorded_at.isoformat(),
            }
            for r in rows
        ]

        total_views = sum(r.views or 0 for r in rows)
        total_likes = sum(r.likes or 0 for r in rows)
        latest = rows[-1] if rows else None
        first = rows[0] if rows else None

        summary = {
            "documentId": str(document_id),
            "title": title,
            "timePoints": len(rows),
            "totalViews": total_views,
            "totalLikes": total_likes,
            "latestViews": latest.views if latest else 0,
            "latestLikes": latest.likes if latest else 0,
            "engagementRate": round(total_likes / max(total_views, 1) * 100, 1),
            "daysTracked": (latest.recorded_at.date() - first.recorded_at.date()).days if latest and first else 0,
        }

        try:
            insights = await self._llm_analyze(title, summary)
            summary["insights"] = insights
            summary["llmAnalyzed"] = True
        except Exception as e:
            logger.warning("LLM analysis failed for doc %s: %s", document_id, e)
            summary["insights"] = "分析暂时不可用"
            summary["llmAnalyzed"] = False

        summary["generatedAt"] = datetime.now(timezone.utc).isoformat()
        summary["metricsSnapshot"] = metrics_data
        return summary

    async def _llm_analyze(self, title: str, summary: dict) -> str:
        from ..prompts.registry import prompt_registry
        from .agent.adapters import DeepSeekLLMAdapter

        rendered = prompt_registry.render(
            "analysis.publish_performance",
            title=title,
            views=str(summary["totalViews"]),
            likes=str(summary["totalLikes"]),
            engagement=str(summary["engagementRate"]),
            days=str(summary["daysTracked"]),
        )
        llm = DeepSeekLLMAdapter()
        raw = await llm.analyze(
            rendered.messages[0].content if rendered.messages else "",
            rendered.messages[1].content if len(rendered.messages) > 1 else "",
        )
        return raw[:500]
