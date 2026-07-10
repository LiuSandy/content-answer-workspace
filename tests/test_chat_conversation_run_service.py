from __future__ import annotations

import asyncio
import contextlib
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.application.agent.collect_results import extract_collect_result
from app.application.agent.process_steps import tool_start_step
from app.application.chat_conversation_run_service import (
    ChatConversationRunService,
    TERMINAL_STATUSES,
)


class ChatConversationRunServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_run_returns_pending_run_with_message_context(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)

        run = await service.create_run("session-1", "帮我采集小红书")

        self.assertTrue(run.id)
        self.assertEqual(run.session_id, "session-1")
        self.assertEqual(run.message, "帮我采集小红书")
        self.assertEqual(run.status, "pending")
        self.assertIs(service.get_run(run.id), run)

    async def test_events_are_monotonic_and_replayable(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")

        first = await service.append_event(run.id, "chunk", {"text": "A"})
        second = await service.append_event(run.id, "done", {"reply": "AB", "collectResults": []})

        self.assertEqual(first.id, 1)
        self.assertEqual(second.id, 2)
        self.assertEqual([event.id for event in service.replay_events(run.id, last_event_id=1)], [2])
        self.assertEqual(len(service.replay_events(run.id, last_event_id=2)), 0)

    async def test_heartbeat_is_not_stored_and_does_not_consume_ids(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")

        heartbeat = await service.append_event(run.id, "heartbeat", {"ts": "now"})
        chunk = await service.append_event(run.id, "chunk", {"text": "A"})

        self.assertIsNone(heartbeat)
        self.assertEqual(chunk.id, 1)
        self.assertEqual([event.event for event in service.replay_events(run.id)], ["chunk"])

    async def test_complete_run_sets_reply_collect_results_and_done_event(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")
        collect_results = [{"platform": "zhihu", "items": [{"title": "A"}]}]

        done = await service.complete_run(run.id, "最终回答", collect_results)

        snapshot = service.get_run_snapshot(run.id)
        assert snapshot is not None
        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["reply"], "最终回答")
        self.assertEqual(snapshot["collectResults"], collect_results)
        self.assertEqual(snapshot["lastEventId"], 1)
        self.assertIsNotNone(snapshot["expiresAt"])
        self.assertEqual(done.event, "done")
        self.assertEqual(done.data, {"reply": "最终回答", "collectResults": collect_results})

    async def test_mark_error_uses_chat_error_business_event(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")

        error = await service.mark_error(run.id, "LLM failed")

        snapshot = service.get_run_snapshot(run.id)
        assert snapshot is not None
        self.assertEqual(snapshot["status"], "error")
        self.assertEqual(snapshot["error"], "LLM failed")
        self.assertEqual(error.event, "chat_error")
        self.assertNotIn("error", [event.event for event in service.replay_events(run.id)])

    async def test_cancel_run_writes_canceled_event_and_terminal_status(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")

        canceled = await service.cancel_run(run.id)

        self.assertEqual(canceled.status, "canceled")
        self.assertEqual(service.replay_events(run.id)[-1].event, "canceled")
        self.assertIsNotNone(canceled.expires_at)

    async def test_cancel_run_cancels_retained_background_task(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")
        graph = _BlockingConversationGraph()

        task = service.start_conversation_run(run.id, graph, lambda session_id, title: None)
        await graph.started.wait()

        canceled = await service.cancel_run(run.id)

        with contextlib.suppress(asyncio.CancelledError):
            await task

        self.assertEqual(canceled.status, "canceled")
        self.assertTrue(task.cancelled())
        self.assertTrue(graph.cancelled)
        self.assertNotIn(run.id, service._tasks)

    async def test_background_task_handle_is_removed_when_done(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")
        graph = _FakeConversationGraph(
            [{"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="ok")}}],
        )

        task = service.start_conversation_run(run.id, graph, lambda session_id, title: None)
        await task

        self.assertEqual(run.status, "done")
        self.assertNotIn(run.id, service._tasks)

    async def test_canceled_run_rejects_later_business_events_and_terminal_updates(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")
        await service.cancel_run(run.id)
        original_events = list(service.replay_events(run.id))

        appended = await service.append_event(run.id, "chunk", {"text": "late"})
        await service.complete_run(run.id, "late reply", [])
        await service.mark_error(run.id, "late error")

        self.assertIsNone(appended)
        self.assertEqual(run.status, "canceled")
        self.assertIsNone(run.reply)
        self.assertIsNone(run.error)
        self.assertEqual(service.replay_events(run.id), original_events)

    async def test_done_run_rejects_later_error_event_and_status_change(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")
        await service.complete_run(run.id, "final", [])
        original_events = list(service.replay_events(run.id))

        await service.mark_error(run.id, "late error")

        self.assertEqual(run.status, "done")
        self.assertEqual(run.reply, "final")
        self.assertIsNone(run.error)
        self.assertEqual(service.replay_events(run.id), original_events)
        self.assertNotIn("chat_error", [event.event for event in service.replay_events(run.id)])

    async def test_error_run_rejects_later_done_event_and_status_change(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")
        await service.mark_error(run.id, "LLM failed")
        original_events = list(service.replay_events(run.id))

        await service.complete_run(run.id, "late reply", [])

        self.assertEqual(run.status, "error")
        self.assertEqual(run.error, "LLM failed")
        self.assertIsNone(run.reply)
        self.assertEqual(service.replay_events(run.id), original_events)
        self.assertNotIn("done", [event.event for event in service.replay_events(run.id)])

    async def test_racing_terminal_updates_create_exactly_one_terminal_event(self) -> None:
        terminal_event_to_status = {
            "done": "done",
            "chat_error": "error",
            "canceled": "canceled",
        }

        for _ in range(20):
            service = ChatConversationRunService(retention_minutes=30, max_runs=10)
            run = await service.create_run("session-1", "hello")

            results = await asyncio.gather(
                service.complete_run(run.id, "final", []),
                service.mark_error(run.id, "LLM failed"),
                service.cancel_run(run.id),
                return_exceptions=True,
            )

            self.assertFalse(any(isinstance(result, Exception) for result in results))
            terminal_events = [
                event
                for event in service.replay_events(run.id)
                if event.event in terminal_event_to_status
            ]
            self.assertEqual(len(terminal_events), 1)
            self.assertEqual(run.status, terminal_event_to_status[terminal_events[0].event])
            self.assertIsNotNone(run.expires_at)

    async def test_wait_for_event_returns_events_after_requested_id(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")

        async def append_later() -> None:
            await asyncio.sleep(0.01)
            await service.append_event(run.id, "chunk", {"text": "A"})

        task = asyncio.create_task(append_later())
        events = await service.wait_for_event(run.id, after_event_id=0, timeout=1)
        await task

        self.assertEqual([event.id for event in events], [1])

    async def test_cleanup_removes_only_expired_terminal_runs(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        done_run = await service.create_run("session-done", "done")
        pending_run = await service.create_run("session-pending", "pending")
        running_run = await service.create_run("session-running", "running")
        running_run.status = "running"

        await service.complete_run(done_run.id, "ok", [])
        done_run.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        pending_run.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        running_run.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        service.cleanup_expired()

        self.assertIsNone(service.get_run(done_run.id))
        self.assertIsNotNone(service.get_run(pending_run.id))
        self.assertIsNotNone(service.get_run(running_run.id))
        self.assertEqual(TERMINAL_STATUSES, {"done", "error", "canceled"})

    async def test_cleanup_expired_removes_retained_task_handle(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")
        task = asyncio.create_task(asyncio.sleep(60))
        service._tasks[run.id] = task
        run.status = "canceled"
        run.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        service.cleanup_expired()

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self.assertIsNone(service.get_run(run.id))
        self.assertNotIn(run.id, service._tasks)

    async def test_run_conversation_streams_tool_collect_chunks_and_done(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "采集知乎话题")
        collect_payload = {
            "platform": "zhihu",
            "topic": "AI",
            "items": [{"title": "A", "url": "https://example.com/a"}],
        }
        graph = _FakeConversationGraph([
            {"event": "on_tool_start", "name": "zhihu_search", "data": {}},
            {
                "event": "on_tool_end",
                "name": "zhihu_search",
                "data": {"output": SimpleNamespace(content=_json_collect_output(collect_payload))},
            },
            {"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="你好")}},
            {"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="世界")}},
        ])
        title_updates: list[tuple[str, str]] = []

        await service.run_conversation(run.id, graph, lambda session_id, title: title_updates.append((session_id, title)))

        events = service.replay_events(run.id)
        self.assertEqual(
            [event.event for event in events],
            ["tool_start", "tool_end", "collect_result", "chunk", "chunk", "done"],
        )
        self.assertEqual(events[0].data, {"text": tool_start_step("zhihu_search"), "name": "zhihu_search"})
        self.assertEqual(events[2].data, collect_payload)
        self.assertEqual(events[-1].data["reply"], "你好世界")
        self.assertEqual(events[-1].data["collectResults"], [collect_payload])
        self.assertEqual(run.status, "done")
        self.assertEqual(graph.received_payload, {"messages": [{"role": "user", "content": "采集知乎话题"}]})
        self.assertEqual(graph.received_config, {"configurable": {"thread_id": "session-1"}})
        self.assertEqual(graph.received_version, "v2")
        self.assertEqual(title_updates, [("session-1", "采集知乎话题")])

    async def test_run_conversation_does_not_update_title_for_existing_thread(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "继续聊")
        graph = _FakeConversationGraph(
            [{"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="ok")}}],
            existing_messages=["previous"],
        )
        title_updates: list[tuple[str, str]] = []

        await service.run_conversation(run.id, graph, lambda session_id, title: title_updates.append((session_id, title)))

        self.assertEqual(title_updates, [])
        self.assertEqual(run.status, "done")

    async def test_run_conversation_marks_error_when_graph_raises(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")
        graph = _FailingConversationGraph(RuntimeError("LLM failed"))

        await service.run_conversation(run.id, graph, lambda session_id, title: None)

        events = service.replay_events(run.id)
        self.assertEqual(run.status, "error")
        self.assertEqual(events[-1].event, "chat_error")
        self.assertEqual(events[-1].data, {"message": "LLM failed"})

    async def test_run_conversation_stops_without_done_when_run_is_canceled(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        run = await service.create_run("session-1", "hello")

        async def cancel_after_first_chunk() -> None:
            await service.cancel_run(run.id)

        graph = _FakeConversationGraph(
            [
                {"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="first")}},
                {"event": "on_chat_model_stream", "data": {"chunk": SimpleNamespace(content="late")}},
            ],
            after_event=cancel_after_first_chunk,
        )

        await service.run_conversation(run.id, graph, lambda session_id, title: None)

        events = service.replay_events(run.id)
        self.assertEqual([event.event for event in events], ["chunk", "canceled"])
        self.assertEqual(events[0].data, {"text": "first"})
        self.assertEqual(run.status, "canceled")
        self.assertNotIn("done", [event.event for event in events])


class CollectResultParserTests(unittest.TestCase):
    def test_extract_collect_result_accepts_tool_message_like_content(self) -> None:
        payload = {
            "platform": "zhihu",
            "topic": "AI",
            "items": [{"title": "A"}],
        }

        result = extract_collect_result("zhihu_search", SimpleNamespace(content=_json_collect_output(payload)))

        self.assertEqual(result, payload)

    def test_extract_collect_result_ignores_non_collect_tool_or_empty_items(self) -> None:
        payload = {"platform": "zhihu", "topic": "AI", "items": [{"title": "A"}]}

        self.assertIsNone(extract_collect_result("calculator", _json_collect_output(payload)))
        self.assertIsNone(extract_collect_result("zhihu_search", _json_collect_output({"items": []})))


if __name__ == "__main__":
    unittest.main()


def _json_collect_output(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


class _FakeConversationGraph:
    def __init__(
        self,
        events: list[dict],
        *,
        existing_messages: list | None = None,
        after_event=None,
    ) -> None:
        self.events = events
        self.existing_messages = existing_messages or []
        self.after_event = after_event
        self.received_payload: dict | None = None
        self.received_config: dict | None = None
        self.received_version: str | None = None

    async def aget_state(self, config: dict) -> SimpleNamespace:
        return SimpleNamespace(values={"messages": self.existing_messages})

    async def astream_events(self, payload: dict, config: dict, version: str):
        self.received_payload = payload
        self.received_config = config
        self.received_version = version
        for event in self.events:
            yield event
            if self.after_event is not None:
                await self.after_event()


class _FailingConversationGraph:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def aget_state(self, config: dict) -> SimpleNamespace:
        return SimpleNamespace(values={"messages": []})

    async def astream_events(self, payload: dict, config: dict, version: str):
        raise self.error
        yield  # pragma: no cover


class _BlockingConversationGraph:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def aget_state(self, config: dict) -> SimpleNamespace:
        return SimpleNamespace(values={"messages": []})

    async def astream_events(self, payload: dict, config: dict, version: str):
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        yield  # pragma: no cover
