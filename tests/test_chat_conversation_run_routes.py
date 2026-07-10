from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.agent import router, set_chat_conversation_run_service
from app.application.chat_conversation_run_service import ChatConversationRunService


def make_client(service: ChatConversationRunService) -> TestClient:
    app = FastAPI()
    set_chat_conversation_run_service(service)
    app.state.conversation_graph = _FakeConversationGraph()
    app.include_router(router)
    return TestClient(app)


class ChatConversationRunRouteTests(unittest.TestCase):
    def test_create_run_returns_envelope(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)

        response = client.post(
            "/api/agent/conversation/runs",
            json={"sessionId": "session-1", "message": "帮我采集知乎"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertIn("runId", body["data"])
        self.assertIn(body["data"]["status"], {"pending", "running"})

    def test_create_run_starts_background_conversation(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        scheduled = []

        def start_conversation_run(run_id: str, graph, update_title):
            scheduled.append((run_id, graph, update_title))
            return SimpleNamespace(done=lambda: False)

        service.start_conversation_run = start_conversation_run  # type: ignore[method-assign]

        with patch("app.api.routes.agent.asyncio.create_task", side_effect=AssertionError("route must delegate task ownership to service")):
            response = client.post(
                "/api/agent/conversation/runs",
                json={"sessionId": "session-1", "message": "帮我采集知乎"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(len(scheduled), 1)
        self.assertIs(scheduled[0][1], client.app.state.conversation_graph)

    def test_get_run_returns_snapshot(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        run = asyncio.run(service.create_run("session-1", "帮我采集知乎"))
        asyncio.run(service.append_event(run.id, "collect_result", {"platform": "zhihu", "items": []}))

        response = client.get(f"/api/agent/conversation/runs/{run.id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["lastEventId"], 1)
        self.assertEqual(data["collectResults"], [])
        self.assertIn("expiresAt", data)

    def test_get_missing_run_returns_clear_error(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)

        response = client.get("/api/agent/conversation/runs/missing")

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["message"], "对话运行不存在或已过期，请重新发送")

    def test_stream_replays_after_query_last_event_id(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        run = asyncio.run(service.create_run("session-1", "帮我采集知乎"))
        asyncio.run(service.append_event(run.id, "chunk", {"text": "a"}))
        asyncio.run(service.complete_run(run.id, "ab", []))

        response = client.get(f"/api/agent/conversation/runs/{run.id}/stream?lastEventId=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
        self.assertIn("id: 2", response.text)
        self.assertIn("event: done", response.text)
        self.assertNotIn("id: 1", response.text)

    def test_stream_last_event_id_header_wins_over_query(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        run = asyncio.run(service.create_run("session-1", "帮我采集知乎"))
        asyncio.run(service.append_event(run.id, "chunk", {"text": "a"}))
        asyncio.run(service.append_event(run.id, "chunk", {"text": "b"}))
        asyncio.run(service.complete_run(run.id, "abc", []))

        response = client.get(
            f"/api/agent/conversation/runs/{run.id}/stream?lastEventId=0",
            headers={"Last-Event-ID": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("id: 2", response.text)
        self.assertIn("id: 3", response.text)
        self.assertNotIn("id: 1", response.text)

    def test_completed_run_stream_closes_after_done(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        run = asyncio.run(service.create_run("session-1", "帮我采集知乎"))
        asyncio.run(service.append_event(run.id, "chunk", {"text": "a"}))
        asyncio.run(service.complete_run(run.id, "a", [{"platform": "zhihu", "items": []}]))

        response = client.get(f"/api/agent/conversation/runs/{run.id}/stream")

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: chunk", response.text)
        self.assertIn("event: done", response.text)
        self.assertNotIn("event: heartbeat", response.text)

    def test_active_stream_waits_then_emits_new_event_via_standard_sse(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        run = asyncio.run(service.create_run("session-1", "帮我采集知乎"))
        original_replay_events = service.replay_events
        replay_lengths: list[int] = []
        wait_calls: list[tuple[str, int]] = []

        def replay_events(run_id: str, last_event_id: int = 0):
            events = original_replay_events(run_id, last_event_id)
            replay_lengths.append(len(events))
            return events

        async def wait_for_event(run_id: str, after_event_id: int, timeout: float = 15.0):
            wait_calls.append((run_id, after_event_id))
            await service.complete_run(run_id, "等待后完成", [])
            return original_replay_events(run_id, after_event_id)

        service.replay_events = replay_events  # type: ignore[method-assign]
        service.wait_for_event = wait_for_event  # type: ignore[method-assign]

        response = client.get(f"/api/agent/conversation/runs/{run.id}/stream")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(wait_calls, [(run.id, 0)])
        self.assertEqual(replay_lengths[:2], [0, 1])
        self.assertIn("id: 1", response.text)
        self.assertIn("event: done", response.text)
        self.assertIn('data: {"reply": "等待后完成", "collectResults": []}', response.text)
        self.assertNotIn("event: heartbeat", response.text)

    def test_idle_running_stream_sends_heartbeat_without_consuming_event_id(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        run = asyncio.run(service.create_run("session-1", "帮我采集知乎"))
        run.status = "running"
        wait_count = 0

        async def wait_for_event(run_id: str, after_event_id: int, timeout: float = 15.0):
            nonlocal wait_count
            wait_count += 1
            if wait_count == 1:
                return []
            await service.complete_run(run_id, "heartbeat 后完成", [])
            return service.replay_events(run_id, after_event_id)

        service.wait_for_event = wait_for_event  # type: ignore[method-assign]

        response = client.get(f"/api/agent/conversation/runs/{run.id}/stream")

        self.assertEqual(response.status_code, 200)
        heartbeat_blocks = [
            block
            for block in response.text.split("\n\n")
            if "event: heartbeat" in block
        ]
        self.assertEqual(len(heartbeat_blocks), 1)
        self.assertNotIn("id:", heartbeat_blocks[0])
        self.assertIn("event: heartbeat", heartbeat_blocks[0])
        self.assertIn("id: 1", response.text)
        self.assertNotIn("id: 2", response.text)
        self.assertEqual(service.get_run_snapshot(run.id)["lastEventId"], 1)  # type: ignore[index]

    def test_missing_run_stream_returns_parseable_chat_error(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)

        response = client.get("/api/agent/conversation/runs/missing/stream")

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: chat_error", response.text)
        self.assertIn("对话运行不存在或已过期，请重新发送", response.text)
        self.assertNotIn("id:", response.text)

    def test_cancel_run_returns_canceled(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        run = asyncio.run(service.create_run("session-1", "帮我采集知乎"))

        response = client.delete(f"/api/agent/conversation/runs/{run.id}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["runId"], run.id)
        self.assertEqual(body["data"]["status"], "canceled")


class LegacyConversationStreamCompatibilityTests(unittest.TestCase):
    def test_legacy_conversation_stream_route_still_uses_data_type_protocol(self) -> None:
        service = ChatConversationRunService(retention_minutes=30, max_runs=10)
        client = make_client(service)
        client.app.state.conversation_graph = _FakeConversationGraph()

        response = client.post(
            "/api/agent/conversation/stream",
            json={"sessionId": "session-1", "message": "继续"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('data: {"type": "chunk"', response.text)
        self.assertIn('data: {"type": "done"', response.text)
        self.assertNotIn("event: chunk", response.text)


class _FakeConversationGraph:
    async def aget_state(self, config: dict) -> SimpleNamespace:
        return SimpleNamespace(values={"messages": ["existing"]})

    async def astream_events(self, payload: dict, config: dict, version: str):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="旧协议")},
        }


if __name__ == "__main__":
    unittest.main()
