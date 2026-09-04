"""OutlineService：观点采访与大纲生命周期（roadmap R6）。

- 大纲与观点快照存入 AIOperation.input_metadata，operation type 为 outline。
- 每个 section 具有稳定 id/order/heading/keyPoints/wordCountEstimate。
- confirmed 快照不可被旧 lock_version 覆盖。
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.dto import (
    AgentError,
    ChatResponsePayload,
)
from app.shared.llm.dto import LLMMessage
from app.shared.errors import DocumentConflictError
from app.modules.conversation.adapters.db.sources import SourceItem
from app.modules.documents.adapters.db.models import AIOperation, AnswerDocument
from .llm import get_writing_llm

logger = logging.getLogger(__name__)

_default_sections: list[dict] = []


@dataclass
class GenerateOutlineResult:
    operation_id: str
    viewpoint_questions: list[str] | None
    outline: list[dict]
    status: str  # draft | confirmed
    version_number: int = 1
    based_on_operation_id: str | None = None


@dataclass
class OutlineError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class OutlineService:
    def __init__(self, session: AsyncSession):
        self._session = session

    # ── 生成 ──────────────────────────────────────────────────────────────

    async def generate(
        self,
        document_id: uuid.UUID,
        source_item_id: uuid.UUID,
        workspace_id: str,
        expected_lock_version: int,
        viewpoint_answers: dict[str, str] | None = None,
        *,
        based_on_operation_id: uuid.UUID | None = None,
        additional_context: str | None = None,
    ) -> GenerateOutlineResult:
        doc = await self._session.get(AnswerDocument, document_id)
        if not doc:
            raise OutlineError("not_found", "Document not found")
        if doc.lock_version != expected_lock_version:
            raise DocumentConflictError(
                expected=expected_lock_version, actual=doc.lock_version
            )

        source = await self._session.get(SourceItem, source_item_id)
        source_content = source.content or "" if source else ""

        try:
            questions, sections = await self._llm_generate(
                source_content + (f"\n\n{additional_context}" if additional_context else ""),
                viewpoint_answers,
            )
        except ValueError as exc:
            raise OutlineError("generation_failed", f"大纲生成失败：{exc}") from exc

        version_number = await self._next_version_number(document_id)
        operation = AIOperation(
            id=uuid.uuid4(),
            document_id=document_id,
            operation_type="outline",
            status="completed",
            input_metadata={
                "outlineStatus": "draft",
                "viewpointQuestions": questions,
                "viewpointAnswers": viewpoint_answers or {},
                "outline": sections,
                "sourceItemId": str(source_item_id),
                "documentLockVersion": expected_lock_version,
                "outlineVersion": version_number,
                "basedOnOperationId": (
                    str(based_on_operation_id) if based_on_operation_id else None
                ),
            },
            completed_at=datetime.now(timezone.utc),
        )
        self._session.add(operation)
        await self._session.flush()
        doc.current_outline_operation_id = operation.id
        await self._session.commit()
        await self._session.refresh(operation)

        return GenerateOutlineResult(
            operation_id=str(operation.id),
            viewpoint_questions=questions,
            outline=sections,
            status="draft",
            version_number=version_number,
            based_on_operation_id=(
                str(based_on_operation_id) if based_on_operation_id else None
            ),
        )

    # ── 获取当前大纲 ──────────────────────────────────────────────────────

    async def get_current(self, document_id: uuid.UUID) -> GenerateOutlineResult | None:
        op = await self._get_current_op(document_id)
        if not op:
            return None
        return await self._result_from_op(document_id, op)

    async def list_versions(self, document_id: uuid.UUID) -> list[GenerateOutlineResult]:
        ops = await self._list_ops(document_id)
        version_numbers = self._version_numbers(ops)
        results = [
            self._result_from_op_with_version(op, version_numbers[op.id])
            for op in ops
        ]
        return sorted(results, key=lambda item: item.version_number, reverse=True)

    async def activate(
        self,
        document_id: uuid.UUID,
        operation_id: uuid.UUID,
        expected_lock_version: int,
    ) -> GenerateOutlineResult:
        doc = await self._session.get(AnswerDocument, document_id)
        if not doc:
            raise OutlineError("not_found", "Document not found")
        if doc.lock_version != expected_lock_version:
            raise DocumentConflictError(
                expected=expected_lock_version, actual=doc.lock_version
            )
        op = await self._session.get(AIOperation, operation_id)
        if (
            op is None
            or op.document_id != document_id
            or op.operation_type != "outline"
        ):
            raise OutlineError("not_found", "Outline version not found")
        doc.current_outline_operation_id = op.id
        await self._session.commit()
        return await self._result_from_op(document_id, op)

    # ── 编辑大纲 ────────────────────────────────────────────────────────

    async def update(
        self,
        document_id: uuid.UUID,
        sections: list[dict],
        viewpoint_answers: dict[str, str] | None,
        expected_lock_version: int,
    ) -> GenerateOutlineResult:
        current = await self._get_current_op(document_id)
        if not current:
            raise OutlineError("not_found", "No outline to update")
        await self._check_confirmed_not_stale(
            current, document_id, expected_lock_version
        )

        version_number = await self._next_version_number(document_id)
        meta = current.input_metadata or {}
        updated = AIOperation(
            id=uuid.uuid4(),
            document_id=document_id,
            operation_type="outline",
            status="completed",
            input_metadata={
                **meta,
                "outline": sections,
                "viewpointAnswers": viewpoint_answers or {},
                "documentLockVersion": expected_lock_version,
                "outlineStatus": "draft",
                "outlineVersion": version_number,
                "basedOnOperationId": str(current.id),
            },
            completed_at=datetime.now(timezone.utc),
        )
        self._session.add(updated)
        doc = await self._session.get(AnswerDocument, document_id)
        if doc is None:
            raise OutlineError("not_found", "Document not found")
        doc.current_outline_operation_id = updated.id
        await self._session.commit()

        return GenerateOutlineResult(
            operation_id=str(updated.id),
            viewpoint_questions=meta.get("viewpointQuestions"),
            outline=sections,
            status="draft",
            version_number=version_number,
            based_on_operation_id=str(current.id),
        )

    # ── 重生成 ──────────────────────────────────────────────────────────

    async def regenerate(
        self,
        document_id: uuid.UUID,
        source_item_id: uuid.UUID,
        workspace_id: str,
        expected_lock_version: int,
        viewpoint_answers: dict[str, str] | None = None,
    ) -> GenerateOutlineResult:
        existing = await self._get_current_op(document_id)
        if existing:
            await self._check_confirmed_not_stale(
                existing, document_id, expected_lock_version
            )

        return await self.generate(
            document_id, source_item_id, workspace_id, expected_lock_version,
            viewpoint_answers=viewpoint_answers,
            based_on_operation_id=existing.id if existing else None,
        )

    # ── 确认 ────────────────────────────────────────────────────────────

    async def confirm(
        self,
        document_id: uuid.UUID,
        expected_lock_version: int,
    ) -> GenerateOutlineResult:
        op = await self._get_current_op(document_id)
        if not op:
            raise OutlineError("not_found", "No outline to confirm")

        doc = await self._session.get(AnswerDocument, document_id)
        if not doc:
            raise OutlineError("not_found", "Document not found")
        if doc.lock_version != expected_lock_version:
            raise DocumentConflictError(
                expected=expected_lock_version, actual=doc.lock_version
            )

        meta = op.input_metadata or {}
        if meta.get("outlineStatus") == "confirmed":
            raise OutlineError("already_confirmed", "Outline already confirmed")

        op.input_metadata = {
            **meta,
            "outlineStatus": "confirmed",
            "documentLockVersion": expected_lock_version,
        }
        await self._session.commit()

        return await self._result_from_op(document_id, op)

    # ── 内部 ────────────────────────────────────────────────────────────

    async def _get_current_op(self, document_id: uuid.UUID) -> AIOperation | None:
        doc = await self._session.get(AnswerDocument, document_id)
        if doc and doc.current_outline_operation_id:
            current = await self._session.get(
                AIOperation, doc.current_outline_operation_id
            )
            if (
                current
                and current.document_id == document_id
                and current.operation_type == "outline"
            ):
                return current
        stmt = (
            select(AIOperation)
            .where(
                AIOperation.document_id == document_id,
                AIOperation.operation_type == "outline",
            )
            .order_by(AIOperation.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _list_ops(self, document_id: uuid.UUID) -> list[AIOperation]:
        stmt = (
            select(AIOperation)
            .where(
                AIOperation.document_id == document_id,
                AIOperation.operation_type == "outline",
            )
            .order_by(AIOperation.created_at.asc(), AIOperation.id.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    @staticmethod
    def _version_numbers(ops: list[AIOperation]) -> dict[uuid.UUID, int]:
        assigned: dict[uuid.UUID, int] = {}
        used: set[int] = set()
        for index, op in enumerate(ops, 1):
            value = (op.input_metadata or {}).get("outlineVersion")
            number = value if isinstance(value, int) and value > 0 else index
            while number in used:
                number += 1
            assigned[op.id] = number
            used.add(number)
        return assigned

    async def _next_version_number(self, document_id: uuid.UUID) -> int:
        ops = await self._list_ops(document_id)
        numbers = self._version_numbers(ops)
        return max(numbers.values(), default=0) + 1

    async def _result_from_op(
        self, document_id: uuid.UUID, op: AIOperation
    ) -> GenerateOutlineResult:
        ops = await self._list_ops(document_id)
        version_number = self._version_numbers(ops).get(op.id, 1)
        return self._result_from_op_with_version(op, version_number)

    @staticmethod
    def _result_from_op_with_version(
        op: AIOperation, version_number: int
    ) -> GenerateOutlineResult:
        meta = op.input_metadata or {}
        return GenerateOutlineResult(
            operation_id=str(op.id),
            viewpoint_questions=meta.get("viewpointQuestions"),
            outline=meta.get("outline") or [],
            status=meta.get("outlineStatus", "draft"),
            version_number=version_number,
            based_on_operation_id=meta.get("basedOnOperationId"),
        )

    async def _check_confirmed_not_stale(
        self, op: AIOperation, document_id: uuid.UUID, expected_lock_version: int
    ) -> None:
        meta = op.input_metadata or {}
        if meta.get("outlineStatus") == "confirmed":
            doc = await self._session.get(AnswerDocument, document_id)
            if doc and doc.lock_version != expected_lock_version:
                raise DocumentConflictError(
                    expected=expected_lock_version, actual=doc.lock_version,
                )

    async def _llm_generate(
        self, source_content: str, viewpoint_answers: dict[str, str] | None
    ) -> tuple[list[str] | None, list[dict]]:
        from app.platform.prompts.registry import prompt_registry

        extra = ""
        if viewpoint_answers:
            answers_text = "\n".join(
                f"  Q: {q}\n  A: {a}" for q, a in viewpoint_answers.items()
            )
            extra = f"\n\n【用户对采访问题的回答】\n{answers_text}"

        rendered = prompt_registry.render(
            "outline.answer_outline",
            source_content=source_content + extra,
        )
        msgs = rendered.to_llm_request().messages
        system_prompt = msgs[0].content if msgs else ""
        user_prompt = msgs[1].content if len(msgs) > 1 else ""

        llm = get_writing_llm()
        raw = await llm.analyze(
            system_prompt,
            user_prompt,
            provider=rendered.provider,
            model=rendered.model,
            temperature=rendered.temperature,
            max_tokens=rendered.max_tokens,
        )
        result = self._parse_outline_json(raw)
        sections = result.get("outline") or []
        if not sections:
            raise ValueError("大纲模型输出为空")
        return result.get("viewpointQuestions"), sections

    @staticmethod
    def parse_outline_json(raw: str) -> dict:
        try:
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            data = json.loads(raw)
        except (json.JSONDecodeError, IndexError) as exc:
            raise ValueError("大纲模型输出不是有效 JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("outline"), list):
            raise ValueError("大纲模型输出缺少有效 outline 字段")
        return data

    _parse_outline_json = parse_outline_json

    @staticmethod
    def _section_id(existing: list[dict], idx: int) -> str:
        for s in existing:
            if s.get("order") == idx + 1:
                return s["id"]
        return str(uuid.uuid4())
