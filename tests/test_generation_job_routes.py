from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.generation_jobs import router, set_generation_job_service
from app.api.routes.stream import generate_one_stream
from app.application.generation_job_service import GenerationJobService
from app.models import QuestionItem, RegeneratePayload


def make_payload(item_id: str = "q-1") -> RegeneratePayload:
    return RegeneratePayload(
        platform="zhihu",
        item=QuestionItem(
            id=item_id,
            platform="zhihu",
            title="如何准备个人网站？",
            url="https://www.zhihu.com/question/1",
            answerCount=3,
            excerpt="摘要",
            detail="详情",
            topic="个人网站",
        ),
        answerStyle="简洁",
        systemPrompt="system",
        generationPrompt="generation",
    )


def make_client(service: GenerationJobService) -> TestClient:
    app = FastAPI()
    set_generation_job_service(service)
    app.include_router(router)
    return TestClient(app)


class GenerationJobRouteTests(unittest.TestCase):
    def test_create_job_returns_envelope(self) -> None:
        service = GenerationJobService(retention_minutes=30, max_jobs=10, autostart=False)
        client = make_client(service)

        response = client.post(
            "/api/workflow/generate-one/jobs",
            json=make_payload().model_dump(by_alias=True),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertIn("jobId", body["data"])
        self.assertIn(body["data"]["status"], {"pending", "running"})

    def test_stream_replays_after_query_last_event_id(self) -> None:
        service = GenerationJobService(retention_minutes=30, max_jobs=10, autostart=False)
        client = make_client(service)
        job = asyncio.run(service.create_generate_one_job(make_payload()))
        asyncio.run(service.append_event(job.id, "chunk", {"text": "a"}))
        asyncio.run(service.mark_done(job.id, {"answer": "ab"}))

        response = client.get(f"/api/workflow/generate-one/jobs/{job.id}/stream?lastEventId=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("id: 2", response.text)
        self.assertIn("event: done", response.text)
        self.assertNotIn("id: 1", response.text)

    def test_stream_last_event_id_header_wins_over_query(self) -> None:
        service = GenerationJobService(retention_minutes=30, max_jobs=10, autostart=False)
        client = make_client(service)
        job = asyncio.run(service.create_generate_one_job(make_payload()))
        asyncio.run(service.append_event(job.id, "chunk", {"text": "a"}))
        asyncio.run(service.append_event(job.id, "chunk", {"text": "b"}))
        asyncio.run(service.mark_done(job.id, {"answer": "ab"}))

        response = client.get(
            f"/api/workflow/generate-one/jobs/{job.id}/stream?lastEventId=0",
            headers={"Last-Event-ID": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("id: 2", response.text)
        self.assertIn("id: 3", response.text)
        self.assertNotIn("id: 1", response.text)

    def test_cancel_job_returns_canceled_snapshot(self) -> None:
        service = GenerationJobService(retention_minutes=30, max_jobs=10, autostart=False)
        client = make_client(service)
        job = asyncio.run(service.create_generate_one_job(make_payload()))

        response = client.delete(f"/api/workflow/generate-one/jobs/{job.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "canceled")


class LegacyStreamCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_generate_one_stream_still_uses_data_type_protocol(self) -> None:
        async def chunks():
            yield "旧"
            yield "协议"

        payload = make_payload()
        with (
            patch(
                "app.api.routes.stream._answer_generator.generate_answer_stream",
                new=lambda *args, **kwargs: chunks(),
            ),
            patch(
                "app.api.routes.stream._image_service.generate_images_for_answer",
                new=AsyncMock(return_value={"images": [], "imagePrompts": []}),
            ),
        ):
            response = await generate_one_stream(payload)
            body = ""
            async for part in response.body_iterator:
                body += part.decode() if isinstance(part, bytes) else part

        self.assertIn('data: {"type": "chunk"', body)
        self.assertIn('data: {"type": "done"', body)
        self.assertNotIn("event: chunk", body)


if __name__ == "__main__":
    unittest.main()
