from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

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


class GenerationJobServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_are_monotonic_and_replayable(self) -> None:
        service = GenerationJobService(retention_minutes=30, max_jobs=10, autostart=False)
        job = await service.create_generate_one_job(make_payload())

        first = await service.append_event(job.id, "chunk", {"text": "第一段"})
        second = await service.append_event(job.id, "done", {"item": {"answer": "第一段"}})
        await service.heartbeat(job.id)

        self.assertEqual(first.id, 1)
        self.assertEqual(second.id, 2)
        self.assertEqual([event.id for event in service.replay_events(job.id, last_event_id=1)], [2])
        self.assertEqual(len(service.replay_events(job.id, last_event_id=2)), 0)

    async def test_duplicate_active_item_returns_same_job(self) -> None:
        service = GenerationJobService(retention_minutes=30, max_jobs=10, autostart=False)
        first = await service.create_generate_one_job(make_payload("same-item"))
        second = await service.create_generate_one_job(make_payload("same-item"))

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.item_id, "same-item")

    async def test_cleanup_removes_only_expired_terminal_jobs(self) -> None:
        service = GenerationJobService(retention_minutes=30, max_jobs=10, autostart=False)
        done_job = await service.create_generate_one_job(make_payload("done-item"))
        running_job = await service.create_generate_one_job(make_payload("running-item"))

        await service.mark_done(done_job.id, {"id": "done-item", "answer": "完成"})
        service._jobs[done_job.id].expires_at = datetime.now(UTC) - timedelta(seconds=1)
        service.cleanup_expired()

        self.assertIsNone(service.get_job(done_job.id))
        self.assertIsNotNone(service.get_job(running_job.id))


async def collect_text_stream():
    for chunk in ("你好", "，世界"):
        yield chunk


async def failing_text_stream():
    raise RuntimeError("LLM failed")
    yield ""


class FakeAnswerGenerator:
    def __init__(self, stream_factory):
        self.stream_factory = stream_factory

    def generate_answer_stream(self, *args, **kwargs):
        return self.stream_factory()


class GenerationJobExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_generate_one_job_emits_chunk_and_done(self) -> None:
        answer_generator = FakeAnswerGenerator(collect_text_stream)
        image_service = AsyncMock()
        image_service.generate_images_for_answer.return_value = {"images": [], "imagePrompts": []}
        service = GenerationJobService(
            retention_minutes=30,
            max_jobs=10,
            autostart=False,
            answer_generator=answer_generator,
            image_service=image_service,
        )
        job = await service.create_generate_one_job(make_payload())

        await service.run_generate_one_job(job.id)

        snapshot = service.get_job_snapshot(job.id)
        assert snapshot is not None
        self.assertEqual(snapshot["status"], "done")
        self.assertEqual(snapshot["finalItem"]["answer"], "你好，世界")
        self.assertEqual([event.event for event in service.replay_events(job.id)], ["chunk", "chunk", "done"])

    async def test_run_generate_one_job_emits_job_error(self) -> None:
        answer_generator = FakeAnswerGenerator(failing_text_stream)
        image_service = AsyncMock()
        service = GenerationJobService(
            retention_minutes=30,
            max_jobs=10,
            autostart=False,
            answer_generator=answer_generator,
            image_service=image_service,
        )
        job = await service.create_generate_one_job(make_payload())

        await service.run_generate_one_job(job.id)

        snapshot = service.get_job_snapshot(job.id)
        assert snapshot is not None
        self.assertEqual(snapshot["status"], "error")
        self.assertEqual(snapshot["error"], "LLM failed")
        self.assertEqual(service.replay_events(job.id)[-1].event, "job_error")

    async def test_canceled_job_is_not_marked_done_after_stream_finishes(self) -> None:
        answer_generator = FakeAnswerGenerator(collect_text_stream)
        image_service = AsyncMock()
        image_service.generate_images_for_answer.return_value = {"images": [], "imagePrompts": []}
        service = GenerationJobService(
            retention_minutes=30,
            max_jobs=10,
            autostart=False,
            answer_generator=answer_generator,
            image_service=image_service,
        )
        job = await service.create_generate_one_job(make_payload())
        await service.cancel_job(job.id)

        await service.run_generate_one_job(job.id)

        snapshot = service.get_job_snapshot(job.id)
        assert snapshot is not None
        self.assertEqual(snapshot["status"], "canceled")


if __name__ == "__main__":
    unittest.main()
