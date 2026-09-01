from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from collections.abc import Callable
from typing import Any, Literal

from app.shared.agent.collect_results import extract_collect_result
from app.shared.agent.process_steps import tool_end_step, tool_start_step
from app.platform.config.runtime import AGENT_MAX_RECURSION

ChatRunStatus = Literal["pending", "running", "done", "error", "canceled"]
ChatRunEventName = Literal[
    "tool_start",
    "tool_end",
    "collect_result",
    "chunk",
    "done",
    "chat_error",
    "canceled",
]

TERMINAL_STATUSES = {"done", "error", "canceled"}
ALLOWED_BUSINESS_EVENTS = {
    "tool_start",
    "tool_end",
    "collect_result",
    "chunk",
    "done",
    "chat_error",
    "canceled",
}

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatSseEvent:
    id: int
    event: ChatRunEventName
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
class ChatConversationRun:
    id: str
    session_id: str
    status: ChatRunStatus
    message: str
    events: list[ChatSseEvent] = field(default_factory=list)
    reply: str | None = None
    collect_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    next_event_id: int = 1

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "runId": self.id,
            "sessionId": self.session_id,
            "status": self.status,
            "message": self.message,
            "reply": self.reply,
            "collectResults": self.collect_results,
            "error": self.error,
            "lastEventId": self.events[-1].id if self.events else 0,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
        }


class ChatConversationRunService:
    def __init__(self, retention_minutes: int = 30, max_runs: int = 200) -> None:
        self.retention = timedelta(minutes=retention_minutes)
        self.max_runs = max_runs
        self._runs: dict[str, ChatConversationRun] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def create_run(self, session_id: str, message: str) -> ChatConversationRun:
        async with self._lock:
            self.cleanup_expired()
            if len(self._runs) >= self.max_runs:
                self.cleanup_expired()
                if len(self._runs) >= self.max_runs:
                    raise ValueError("Chat conversation run cache is full")

            run = ChatConversationRun(
                id=uuid.uuid4().hex,
                session_id=session_id,
                status="pending",
                message=message,
            )
            self._runs[run.id] = run
            self._conditions[run.id] = asyncio.Condition()
            return run

    def get_run(self, run_id: str) -> ChatConversationRun | None:
        return self._runs.get(run_id)

    def get_run_snapshot(self, run_id: str) -> dict[str, Any] | None:
        run = self.get_run(run_id)
        return run.to_snapshot() if run else None

    def replay_events(self, run_id: str, last_event_id: int = 0) -> list[ChatSseEvent]:
        run = self._runs.get(run_id)
        if not run:
            return []
        return [event for event in run.events if event.id > last_event_id]

    async def append_event(
        self,
        run_id: str,
        event: str,
        data: dict[str, Any],
    ) -> ChatSseEvent | None:
        if event == "heartbeat":
            self._get_required_run(run_id)
            return None
        if event not in ALLOWED_BUSINESS_EVENTS:
            raise ValueError(f"Unsupported chat conversation event: {event}")

        async with self._lock:
            run = self._get_required_run(run_id)
            if run.status in TERMINAL_STATUSES:
                return None
            created = self._append_event_locked(run, event, data)
            run.updated_at = created.created_at
            if run.status == "pending":
                run.status = "running"

        await self._notify(run_id)
        return created

    async def wait_for_event(
        self,
        run_id: str,
        after_event_id: int,
        timeout: float = 15.0,
    ) -> list[ChatSseEvent]:
        condition = self._conditions.get(run_id)
        if condition is None:
            return []
        try:
            async with condition:
                await asyncio.wait_for(
                    condition.wait_for(
                        lambda: bool(self.replay_events(run_id, after_event_id)) or self._is_terminal(run_id)
                    ),
                    timeout=timeout,
                )
        except TimeoutError:
            return []
        return self.replay_events(run_id, after_event_id)

    async def run_conversation(
        self,
        run_id: str,
        graph: Any,
        update_title: Callable[[str, str], Any],
    ) -> None:
        try:
            run = self._get_required_run(run_id)
            session_id = run.session_id
            message = run.message
            config = {
                "configurable": {"thread_id": session_id},
                "recursion_limit": AGENT_MAX_RECURSION,
            }
            existing_state = await graph.aget_state(config)
            state_values = getattr(existing_state, "values", {}) or {}
            is_first_message = not state_values.get("messages")
            full_reply = ""
            collect_results: list[dict[str, Any]] = []

            async for event in graph.astream_events(
                {"messages": [{"role": "user", "content": message}]},
                config=config,
                version="v2",
            ):
                if self._is_canceled(run_id):
                    return

                kind = event.get("event")
                if kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    await self.append_event(
                        run_id,
                        "tool_start",
                        {"text": tool_start_step(tool_name), "name": tool_name},
                    )
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "")
                    await self.append_event(
                        run_id,
                        "tool_end",
                        {"text": tool_end_step(tool_name), "name": tool_name},
                    )
                    if self._is_canceled(run_id):
                        return
                    collect_result = extract_collect_result(
                        tool_name,
                        (event.get("data") or {}).get("output", ""),
                    )
                    if collect_result is not None:
                        collect_results.append(collect_result)
                        await self.append_event(run_id, "collect_result", collect_result)
                elif kind == "on_chat_model_stream":
                    chunk = (event.get("data") or {}).get("chunk")
                    text = getattr(chunk, "content", "") if chunk is not None else ""
                    if text:
                        full_reply += text
                        await self.append_event(run_id, "chunk", {"text": text})

            if self._is_canceled(run_id):
                return
            await self.complete_run(run_id, full_reply, collect_results)

            if is_first_message:
                result = update_title(session_id, message[:20])
                if inspect.isawaitable(result):
                    await result
        except Exception as exc:  # noqa: BLE001
            await self.mark_error(run_id, str(exc))

    def start_conversation_run(
        self,
        run_id: str,
        graph: Any,
        update_title: Callable[[str, str], Any],
    ) -> asyncio.Task[None]:
        previous_task = self._tasks.get(run_id)
        if previous_task is not None and not previous_task.done():
            previous_task.cancel()

        task = asyncio.create_task(self.run_conversation(run_id, graph, update_title))
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed: self._discard_task(run_id, completed))
        return task

    async def complete_run(
        self,
        run_id: str,
        reply: str,
        collect_results: list[dict[str, Any]],
    ) -> ChatSseEvent | None:
        async with self._lock:
            run = self._get_required_run(run_id)
            if run.status in TERMINAL_STATUSES:
                return None
            run.reply = reply
            run.collect_results = collect_results
            event = self._append_event_locked(run, "done", {"reply": reply, "collectResults": collect_results})
            self._mark_terminal_locked(run, "done", event.created_at)

        await self._notify(run_id)
        return event

    async def mark_error(self, run_id: str, message: str) -> ChatSseEvent | None:
        async with self._lock:
            run = self._get_required_run(run_id)
            if run.status in TERMINAL_STATUSES:
                return None
            run.error = message
            event = self._append_event_locked(run, "chat_error", {"message": message})
            self._mark_terminal_locked(run, "error", event.created_at)

        await self._notify(run_id)
        return event

    async def cancel_run(self, run_id: str) -> ChatConversationRun:
        task: asyncio.Task[None] | None = None
        async with self._lock:
            task = self._tasks.pop(run_id, None)
            run = self._get_required_run(run_id)
            if run.status in TERMINAL_STATUSES:
                if task is not None and not task.done():
                    task.cancel()
                return run
            event = self._append_event_locked(run, "canceled", {"message": "对话已取消"})
            self._mark_terminal_locked(run, "canceled", event.created_at)

        if task is not None and not task.done():
            task.cancel()
        await self._notify(run_id)
        return self._get_required_run(run_id)

    def cleanup_expired(self) -> None:
        now = datetime.now(UTC)
        expired_ids = [
            run_id
            for run_id, run in self._runs.items()
            if run.status in TERMINAL_STATUSES and run.expires_at is not None and run.expires_at <= now
        ]
        for run_id in expired_ids:
            self._runs.pop(run_id, None)
            self._conditions.pop(run_id, None)
            task = self._tasks.pop(run_id, None)
            if task is not None and not task.done():
                task.cancel()

    def _get_required_run(self, run_id: str) -> ChatConversationRun:
        run = self._runs.get(run_id)
        if not run:
            raise KeyError(run_id)
        return run

    def _append_event_locked(
        self,
        run: ChatConversationRun,
        event: str,
        data: dict[str, Any],
    ) -> ChatSseEvent:
        created = ChatSseEvent(
            id=run.next_event_id,
            event=event,  # type: ignore[arg-type]
            data=data,
            created_at=datetime.now(UTC),
        )
        run.next_event_id += 1
        run.events.append(created)
        return created

    def _mark_terminal_locked(
        self,
        run: ChatConversationRun,
        status: ChatRunStatus,
        updated_at: datetime,
    ) -> None:
        run.status = status
        run.updated_at = updated_at
        run.expires_at = updated_at + self.retention

    async def _notify(self, run_id: str) -> None:
        condition = self._conditions.get(run_id)
        if condition is None:
            return
        async with condition:
            condition.notify_all()

    def _is_terminal(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        return run is None or run.status in TERMINAL_STATUSES

    def _is_canceled(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        return run is None or run.status == "canceled"

    def _discard_task(self, run_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(run_id) is task:
            self._tasks.pop(run_id, None)
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception is not None:
            logger.error(
                "Chat conversation background task failed",
                exc_info=(type(exception), exception, exception.__traceback__),
            )
