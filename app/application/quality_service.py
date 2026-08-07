"""QualityService：生成后质检 → 查看报告 → 逐条采纳 → 新版本（roadmap R3）。

- review()：LLM 结构化评审，报告写入 quality_review AIOperation 的 output_metadata。
- adopt_suggestion()：逐条采纳建议，生成 version_type=inline_refinement 新版本，
  落一条 quality_adopt AIOperation 并回填 result_version_id，供 StyleLearner 溯源。
- 来源版本锁定：报告基于的版本必须仍是当前版本，否则拒绝采纳；
  同时沿用乐观锁 expected_lock_version，不覆盖并发编辑。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.dto import QualityReport
from ..errors import LLMOutputError
from ..persistence.models.documents import (
    VERSION_TYPE_INLINE_REFINEMENT,
    AIOperation,
    AnswerDocument,
    AnswerVersion,
)
from .document_service import DocumentService

QUALITY_REVIEW_PROMPT = "review.quality_review"


def _get_llm():
    """延迟导入避免循环引用；测试可 monkeypatch 本函数注入 mock。"""
    from app.application.agent.adapters import DeepSeekLLMAdapter

    return DeepSeekLLMAdapter()


class QualityReviewError(Exception):
    """质检业务错误；message 直接面向用户。"""


@dataclass
class QualityReviewResult:
    """一次质检的结果；report_id 指向落库的 quality_review AIOperation。"""

    report_id: str
    report: QualityReport
    source_version_id: str | None


class QualityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._doc_service = DocumentService(session)

    # ── 质检 ────────────────────────────────────────────────────────────────

    async def review(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
        workspace_id: str = "default",
    ) -> QualityReviewResult:
        """对文档当前内容执行一次质检评审。

        报告完整写入 quality_review AIOperation.output_metadata；结构化失败时
        落库 failed 操作并抛 LLMOutputError。
        """
        doc = await self._doc_service.get_document(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        content = doc.current_content or ""
        if not content.strip():
            raise QualityReviewError("文档内容为空，无法质检")

        source_version_id = version_id if version_id is not None else doc.current_version_id
        source_version_key = str(source_version_id) if source_version_id else None

        llm = _get_llm()
        from ..prompts.registry import prompt_registry

        rendered = prompt_registry.render(QUALITY_REVIEW_PROMPT, content=content)
        messages = rendered.to_llm_request().messages
        system_prompt = messages[0].content if messages else ""
        user_prompt = messages[1].content if len(messages) > 1 else content

        result = await llm.generate_structured(
            schema=QualityReport,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        if result.value is None:
            op = AIOperation(
                document_id=doc.id,
                operation_type="quality_review",
                status="failed",
                prompt_id=QUALITY_REVIEW_PROMPT,
                model_parameters={
                    "methodUsed": result.method_used,
                    "attempts": result.attempts,
                    "degradationReason": result.degradation_reason,
                },
                input_metadata={"sourceVersionId": source_version_key},
                error_code="llm_output_error",
                error_message=result.degradation_reason or "structured generation failed",
            )
            self._session.add(op)
            await self._session.commit()
            raise LLMOutputError(
                result.degradation_reason or "质检结构化输出失败，请重试"
            )

        op = AIOperation(
            document_id=doc.id,
            operation_type="quality_review",
            status="completed",
            prompt_id=QUALITY_REVIEW_PROMPT,
            model_parameters={
                "methodUsed": result.method_used,
                "attempts": result.attempts,
                "degradationReason": result.degradation_reason,
            },
            input_metadata={"sourceVersionId": source_version_key},
            output_metadata={
                "report": result.value.model_dump(mode="json", by_alias=True),
            },
        )
        self._session.add(op)
        await self._session.commit()
        await self._session.refresh(op)

        return QualityReviewResult(
            report_id=str(op.id),
            report=result.value,
            source_version_id=source_version_key,
        )

    # ── 采纳 ────────────────────────────────────────────────────────────────

    async def adopt_suggestion(
        self,
        document_id: uuid.UUID,
        report_id: str,
        suggestion_id: str,
        expected_lock_version: int,
    ) -> AnswerVersion:
        """逐条采纳建议，生成 inline_refinement 新版本并落 quality_adopt 操作。

        幂等：同一 (report, suggestion) 已被采纳时直接返回既有版本。
        """
        op = await self._session.get(AIOperation, uuid.UUID(report_id))
        if op is None or op.operation_type != "quality_review":
            raise QualityReviewError("质检报告不存在")
        if op.status != "completed":
            raise QualityReviewError("质检报告尚未完成")

        report_data = (op.output_metadata or {}).get("report")
        if not report_data:
            raise QualityReviewError("质检报告数据缺失")
        report = QualityReport.model_validate(report_data)

        doc = await self._doc_service.get_document(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        suggestion = next((s for s in report.quality_suggestions if s.id == suggestion_id), None)
        if suggestion is None:
            raise QualityReviewError("建议不存在或已失效")
        if not suggestion.replacement:
            raise QualityReviewError("该建议没有可采纳的替换文本")

        # 幂等：已采纳过则直接返回既有版本，不重复写库（优先于来源版本锁定）
        existing = await self._find_adopted(report_id, suggestion_id)
        if existing is not None:
            return existing

        # 来源版本锁定：报告基于的版本必须是当前版本
        source_version_key = (op.input_metadata or {}).get("sourceVersionId")
        current_version_key = str(doc.current_version_id) if doc.current_version_id else None
        if source_version_key and source_version_key != current_version_key:
            raise QualityReviewError("报告基于的版本已不是当前版本，请重新质检")

        content = doc.current_content or ""
        new_content = suggestion.replacement
        if suggestion.anchor:
            if suggestion.anchor not in content:
                raise QualityReviewError(
                    "原文片段已发生变化，无法采纳该建议，请重新质检",
                )
            new_content = content.replace(suggestion.anchor, suggestion.replacement, 1)

        version = await self._doc_service.create_version(
            document_id=document_id,
            content=new_content,
            version_type=VERSION_TYPE_INLINE_REFINEMENT,
            expected_lock_version=expected_lock_version,
            instruction=suggestion.title,
            prompt_id=QUALITY_REVIEW_PROMPT,
        )

        adopt_op = AIOperation(
            document_id=document_id,
            operation_type="quality_adopt",
            status="completed",
            prompt_id=QUALITY_REVIEW_PROMPT,
            input_metadata={
                "reportId": report_id,
                "suggestionId": suggestion_id,
                "sourceVersionId": source_version_key,
            },
            output_metadata={
                "reportId": report_id,
                "suggestionId": suggestion_id,
                "anchor": suggestion.anchor,
            },
            result_version_id=version.id,
        )
        self._session.add(adopt_op)
        await self._session.commit()
        await self._session.refresh(version)
        return version

    async def _find_adopted(self, report_id: str, suggestion_id: str) -> AnswerVersion | None:
        stmt = (
            select(AIOperation)
            .where(AIOperation.operation_type == "quality_adopt")
            .where(AIOperation.result_version_id.is_not(None))
        )
        ops = (await self._session.execute(stmt)).scalars().all()
        for op in ops:
            meta = op.output_metadata or {}
            if meta.get("reportId") == report_id and meta.get("suggestionId") == suggestion_id:
                return await self._session.get(AnswerVersion, op.result_version_id)
        return None

    # ── 报告查询 ────────────────────────────────────────────────────────────

    async def list_quality_scores(self, document_id: uuid.UUID) -> list[dict[str, Any]]:
        """返回某文档全部已完成质检报告（按时间升序），供前端报告列表恢复查询。

        每条建议附带 adopted 标记（该 reportId 下已存在 quality_adopt 操作），
        供前端展示已采纳状态。
        """
        stmt = (
            select(AIOperation)
            .where(AIOperation.document_id == document_id)
            .where(AIOperation.operation_type == "quality_review")
            .where(AIOperation.status == "completed")
            .order_by(AIOperation.created_at.asc())
        )
        ops = (await self._session.execute(stmt)).scalars().all()

        adopt_stmt = (
            select(AIOperation)
            .where(AIOperation.document_id == document_id)
            .where(AIOperation.operation_type == "quality_adopt")
        )
        adopt_ops = (await self._session.execute(adopt_stmt)).scalars().all()
        adopted_by_report: dict[str, set[str]] = {}
        for op in adopt_ops:
            meta = op.output_metadata or {}
            rid = meta.get("reportId")
            sid = meta.get("suggestionId")
            if rid and sid:
                adopted_by_report.setdefault(rid, set()).add(sid)

        rows: list[dict[str, Any]] = []
        for op in ops:
            report_data = (op.output_metadata or {}).get("report") or {}
            suggestions = list(report_data.get("qualitySuggestions") or [])
            adopted = adopted_by_report.get(str(op.id), set())
            for sug in suggestions:
                sug["adopted"] = sug.get("id") in adopted
            rows.append(
                {
                    "reportId": str(op.id),
                    "overallScore": report_data.get("overallScore"),
                    "dimensionScores": report_data.get("dimensionScores"),
                    "issues": report_data.get("issues"),
                    "suggestions": suggestions,
                    "summary": report_data.get("summary"),
                    "sourceVersionId": (op.input_metadata or {}).get("sourceVersionId"),
                    "createdAt": op.created_at.isoformat() if op.created_at else None,
                }
            )
        return rows
