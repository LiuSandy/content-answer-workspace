from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from ..core.config import get_workflow_config, load_env_file
from ..infrastructure.llm.deepseek_client import DeepSeekAnswerGenerator
from ..models import RegeneratePayload
from ..services.image_service import GeneratedImagePayload, ImageGenerationService
from .workflow_service import normalize_platform
from ..observability.context import reset_log_context, set_log_context

JobStatus = Literal["pending", "running", "done", "error", "canceled"]
JobEventName = Literal["chunk", "done", "job_error", "canceled"]

TERMINAL_STATUSES = {"done", "error", "canceled"}


@dataclass(slots=True)
class SseJobEvent:
    id: int
    event: JobEventName
    data: dict[str, Any]
    created_at: datetime

    def to_sse_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event": self.event,
            "data": self.data,
            "createdAt": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class GenerationJob:
    id: str
    kind: Literal["generate_one"]
    status: JobStatus
    item_id: str
    payload: RegeneratePayload
    events: list[SseJobEvent] = field(default_factory=list)
    final_item: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    next_event_id: int = 1

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "jobId": self.id,
            "kind": self.kind,
            "status": self.status,
            "itemId": self.item_id,
            "finalItem": self.final_item,
            "error": self.error,
            "lastEventId": self.events[-1].id if self.events else 0,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
        }


class GenerationJobService:
    def __init__(
        self,
        retention_minutes: int = 30,
        max_jobs: int = 200,
        autostart: bool = True,
        answer_generator: Any | None = None,
        image_service: Any | None = None,
    ) -> None:
        self.retention = timedelta(minutes=retention_minutes)
        self.max_jobs = max_jobs
        self.autostart = autostart
        self._answer_generator = answer_generator or DeepSeekAnswerGenerator()
        self._image_service = image_service or ImageGenerationService()
        self._jobs: dict[str, GenerationJob] = {}
        self._active_by_item_id: dict[str, str] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._lock = asyncio.Lock()

    async def create_generate_one_job(self, payload: RegeneratePayload) -> GenerationJob:
        async with self._lock:
            self.cleanup_expired()
            active_id = self._active_by_item_id.get(payload.item.id)
            active = self._jobs.get(active_id or "")
            if active and active.status in {"pending", "running"}:
                return active
            if len(self._jobs) >= self.max_jobs:
                self.cleanup_expired()
                if len(self._jobs) >= self.max_jobs:
                    raise ValueError("Generation job cache is full")

            job = GenerationJob(
                id=uuid.uuid4().hex,
                kind="generate_one",
                status="pending",
                item_id=payload.item.id,
                payload=payload,
            )
            self._jobs[job.id] = job
            self._active_by_item_id[job.item_id] = job.id
            self._conditions[job.id] = asyncio.Condition()

        if self.autostart:
            asyncio.create_task(self.run_generate_one_job(job.id))
        return job

    def get_job(self, job_id: str) -> GenerationJob | None:
        return self._jobs.get(job_id)

    def get_job_snapshot(self, job_id: str) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        return job.to_snapshot() if job else None

    def replay_events(self, job_id: str, last_event_id: int = 0) -> list[SseJobEvent]:
        job = self._jobs.get(job_id)
        if not job:
            return []
        return [event for event in job.events if event.id > last_event_id]

    async def append_event(self, job_id: str, event: str, data: dict[str, Any]) -> SseJobEvent:
        if event not in {"chunk", "done", "job_error", "canceled"}:
            raise ValueError(f"Unsupported generation job event: {event}")
        async with self._lock:
            job = self._get_required_job(job_id)
            created = SseJobEvent(
                id=job.next_event_id,
                event=event,  # type: ignore[arg-type]
                data=data,
                created_at=datetime.now(UTC),
            )
            job.next_event_id += 1
            job.events.append(created)
            job.updated_at = created.created_at
        await self._notify(job_id)
        return created

    async def heartbeat(self, job_id: str) -> dict[str, str]:
        self._get_required_job(job_id)
        return {"ts": datetime.now(UTC).isoformat()}

    async def mark_done(self, job_id: str, final_item: dict[str, Any]) -> None:
        async with self._lock:
            job = self._get_required_job(job_id)
            if job.status == "canceled":
                return
            job.final_item = final_item
        await self.append_event(job_id, "done", {"item": final_item})
        await self._terminalize(job_id, "done")

    async def mark_error(self, job_id: str, message: str) -> None:
        async with self._lock:
            job = self._get_required_job(job_id)
            if job.status == "canceled":
                return
            job.error = message
        await self.append_event(job_id, "job_error", {"message": message})
        await self._terminalize(job_id, "error")

    async def cancel_job(self, job_id: str) -> GenerationJob:
        async with self._lock:
            job = self._get_required_job(job_id)
            if job.status in TERMINAL_STATUSES:
                return job
        await self.append_event(job_id, "canceled", {"message": "生成已取消"})
        await self._terminalize(job_id, "canceled")
        return self._get_required_job(job_id)

    async def run_generate_one_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job or job.status == "canceled":
            return
        log_token = set_log_context(job_id=job_id)
        try:
            job.status = "running"
            job.updated_at = datetime.now(UTC)
            load_env_file()
            payload = job.payload
            platform = normalize_platform(payload.platform or payload.item.platform)
            item = payload.item.model_copy(update={"platform": platform})
            config = get_workflow_config(
                {
                    "platform": platform,
                    "answerStyle": payload.answer_style,
                    "systemPrompt": payload.system_prompt,
                    "generationPrompt": payload.generation_prompt,
                }
            )

            full_text = ""
            async for chunk in self._answer_generator.generate_answer_stream(
                item,
                payload.answer_style or config.answer_style,
                config.cta_text,
                payload.system_prompt or config.system_prompt,
                payload.generation_prompt or config.generation_prompt,
                payload.content_constraint or None,
            ):
                if self._is_canceled(job_id):
                    return
                full_text += chunk
                await self.append_event(job_id, "chunk", {"text": chunk})

            if self._is_canceled(job_id):
                return
            try:
                images = await self._image_service.generate_images_for_answer(item, full_text)
            except ValueError as error:
                if "Missing required env: IMAGE_" not in str(error):
                    raise
                images = GeneratedImagePayload(images=[], imagePrompts=[])

            if self._is_canceled(job_id):
                return
            final_item = item.model_copy(
                update={
                    "answer": full_text.strip(),
                    "images": images.get("images", []),
                    "image_prompts": images.get("imagePrompts", []),
                }
            )
            await self.mark_done(job_id, final_item.model_dump(by_alias=True))
        except Exception as error:  # noqa: BLE001
            await self.mark_error(job_id, str(error))
        finally:
            reset_log_context(log_token)

    async def wait_for_events(self, job_id: str, last_event_id: int, timeout: float = 15.0) -> list[SseJobEvent]:
        condition = self._conditions.get(job_id)
        if condition is None:
            return []
        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: bool(self.replay_events(job_id, last_event_id)) or self._is_terminal(job_id)),
                timeout=timeout,
            )
        return self.replay_events(job_id, last_event_id)

    def cleanup_expired(self) -> None:
        now = datetime.now(UTC)
        expired_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in TERMINAL_STATUSES and job.expires_at is not None and job.expires_at <= now
        ]
        for job_id in expired_ids:
            job = self._jobs.pop(job_id)
            self._conditions.pop(job_id, None)
            if self._active_by_item_id.get(job.item_id) == job_id:
                self._active_by_item_id.pop(job.item_id, None)

    def _get_required_job(self, job_id: str) -> GenerationJob:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        return job

    async def _terminalize(self, job_id: str, status: JobStatus) -> None:
        async with self._lock:
            job = self._get_required_job(job_id)
            job.status = status
            job.updated_at = datetime.now(UTC)
            job.expires_at = job.updated_at + self.retention
            if self._active_by_item_id.get(job.item_id) == job.id:
                self._active_by_item_id.pop(job.item_id, None)
        await self._notify(job_id)

    async def _notify(self, job_id: str) -> None:
        condition = self._conditions.get(job_id)
        if condition is None:
            return
        async with condition:
            condition.notify_all()

    def _is_canceled(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        return job is None or job.status == "canceled"

    def _is_terminal(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        return job is None or job.status in TERMINAL_STATUSES
