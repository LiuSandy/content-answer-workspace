# Reliable SSE Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reliable single-answer generation job flow that creates background jobs, streams recoverable standard SSE events, resumes after reconnects or refreshes, and keeps streaming preview separate from the final editable answer.

**Architecture:** Add a backend in-memory `GenerationJobService` with per-job event logs, active-item de-duplication, TTL cleanup, cancellation, and standard SSE formatting. Expose thin FastAPI job routes alongside the legacy stream routes, then migrate the workbench single-answer UI to a dedicated EventSource client and per-item generation state while leaving legacy stream clients untouched.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, asyncio, pytest/unittest, React 19, TypeScript, Zustand, TanStack Query, Vite, bun.

---

## 功能概述（Overview）

本计划实现 [docs/specs/feature-reliable-sse-generation.md](../specs/feature-reliable-sse-generation.md) 中定义的可靠 SSE 单条回答生成。范围只覆盖工作台单条回答生成：创建 job、后台生成、标准 SSE 订阅、断点补发、页面刷新恢复、生成中只读预览和完成后编辑器挂载。

旧接口继续存在：

- `POST /api/workflow/generate-one/stream`
- `POST /api/workflow/generate/stream`
- `POST /api/workflow/polish-one/stream`

## 目标（Goal）

交付一个可验证的两阶段单条生成流程：前端创建 job 后通过 `EventSource` 订阅标准 SSE 事件；服务端缓存业务事件并支持 `Last-Event-ID` 和 `?lastEventId=` 补发；工作台 UI 不再把 token 级流式内容写入最终 `answer` 字段。

## 范围（Scope）

会修改：

- 后端：新增 job service、标准 SSE formatter、job routes、server router 挂载、后端测试。
- 前端：新增 job API 类型和 EventSource 客户端、扩展 workbench store、迁移 `WorkbenchAnswerPanel` 的单条生成路径。
- 验证：新增后端单元/路由测试，前端运行 TypeScript typecheck，并保留手工端到端验证清单。

不会修改：

- LLM prompt、回答质量策略、采集、URL 导入、热榜、Agent 对话。
- 批量生成和润色的旧流式接口。
- `frontend/src/lib/sse.ts` 的旧 `fetch + ReadableStream` 解析路径。
- 跨进程持久化或服务重启后的 job 恢复。

## 技术栈（Tech Stack）

- Backend: Python 3.11, FastAPI, `StreamingResponse`, `asyncio.Lock`, `asyncio.Condition`, dataclasses, Pydantic model serialization.
- Backend tests: `unittest.IsolatedAsyncioTestCase`, `pytest`, `fastapi.testclient.TestClient`, `unittest.mock.AsyncMock`.
- Frontend: React 19, TypeScript, Zustand, TanStack Query, `EventSource`, `sessionStorage`.
- Frontend verification: `bun run typecheck`, manual browser checks against Vite and FastAPI.

## 涉及文件（Files）

- Create: `app/application/generation_job_service.py`
  - Owns `GenerationJob`, `SseJobEvent`, `GenerationJobService`, job lifecycle, event cache, active item de-duplication, TTL cleanup, and background generation orchestration.
- Create: `app/api/routes/generation_jobs.py`
  - Thin FastAPI routes for `POST /api/workflow/generate-one/jobs`, `GET /api/workflow/generate-one/jobs/{job_id}`, `GET /api/workflow/generate-one/jobs/{job_id}/stream`, and `DELETE /api/workflow/generate-one/jobs/{job_id}`.
- Modify: `app/api/sse_utils.py`
  - Add standard SSE event formatter while keeping the old `sse_event(payload)` function unchanged.
- Modify: `app/server.py`
  - Include the new generation job router.
- Create: `tests/test_generation_job_service.py`
  - Unit tests for event ids, replay, de-duplication, error, cancel, and cleanup.
- Create: `tests/test_generation_job_routes.py`
  - Route tests for envelope responses, stream replay, `Last-Event-ID`, `?lastEventId=`, and legacy route compatibility.
- Modify: `frontend/src/types/workflow.ts`
  - Add job response, snapshot, SSE event, and per-item generation state types; extend `GenerationStatus` with `creating` and `canceled`.
- Modify: `frontend/src/features/workspace/workflow-api.ts`
  - Add create/get/cancel job API functions. Keep legacy stream API functions unchanged.
- Create: `frontend/src/features/workspace/generation-job-client.ts`
  - Own EventSource subscription, duplicate event filtering, reconnect timer, `sessionStorage` persistence helpers, and callback contract for workbench.
- Modify: `frontend/src/store/workbench-store.ts`
  - Add actions for job state, streaming preview, final answer, cancellation, interruption, and session restore.
- Modify: `frontend/src/features/workbench/workbench-answer-panel.tsx`
  - Migrate single-answer generation from `streamGenerateOneAnswer` to job creation + EventSource subscription; render preview while generating and mount `MarkdownEditor` only after completion.

## 任务拆分（Tasks）

### Task 1: Backend job service event model and replay

**目标：**
Create the backend in-memory job/event core without LLM execution. This task proves event ids, standard SSE payload data, replay from `lastEventId`, active item de-duplication, and TTL cleanup.

**涉及文件：**
- Create: `app/application/generation_job_service.py`
- Test: `tests/test_generation_job_service.py`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`tests/test_generation_job_service.py`
  - 测试内容：create a job, append events, assert ids are monotonic, replay skips old ids, heartbeat is not stored, duplicate active item returns the same job, cleanup preserves running jobs.
  - Add this test file:

```python
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

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


if __name__ == "__main__":
    unittest.main()
```

  - 运行命令：`uv run pytest tests/test_generation_job_service.py -v`
  - 预期结果：测试失败，失败原因包含 `ModuleNotFoundError: No module named 'app.application.generation_job_service'`。

- [ ] Step 2: 写最小实现
  - 文件：`app/application/generation_job_service.py`
  - 实现内容：create dataclasses and a service API matching the tests. Include these public methods and fields:

```python
TERMINAL_STATUSES = {"done", "error", "canceled"}

@dataclass(slots=True)
class SseJobEvent:
    id: int
    event: Literal["chunk", "done", "job_error", "canceled"]
    data: dict[str, Any]
    created_at: datetime

@dataclass(slots=True)
class GenerationJob:
    id: str
    kind: Literal["generate_one"]
    status: Literal["pending", "running", "done", "error", "canceled"]
    item_id: str
    payload: RegeneratePayload
    events: list[SseJobEvent] = field(default_factory=list)
    final_item: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    next_event_id: int = 1

class GenerationJobService:
    # Implement these public methods in Task 1:
    # __init__(retention_minutes, max_jobs, autostart)
    # create_generate_one_job(payload)
    # get_job(job_id)
    # replay_events(job_id, last_event_id)
    # append_event(job_id, event, data)
    # heartbeat(job_id)
    # mark_done(job_id, final_item)
    # mark_error(job_id, message)
    # cancel_job(job_id)
    # cleanup_expired()
```

  - Use `uuid.uuid4().hex` for job ids.
  - Use `_active_by_item_id: dict[str, str]` to return an existing `pending` or `running` job for the same item.
  - Do not call LLM in this task.

- [ ] Step 3: 运行测试
  - 命令：`uv run pytest tests/test_generation_job_service.py -v`
  - 预期结果：Task 1 tests pass.

- [ ] Step 4: 重构
  - 文件：`app/application/generation_job_service.py`
  - Keep event serialization separate from storage by adding `SseJobEvent.to_sse_data()` and `GenerationJob.to_snapshot()` methods.
  - Do not add routes or LLM execution in this task.

- [ ] Step 5: 再次验证
  - 命令：`uv run pytest tests/test_generation_job_service.py -v`
  - 预期结果：all Task 1 tests pass.

- [ ] Step 6: 提交
  - 提交信息：`feat: add generation job event store`

### Task 2: Backend generation execution and terminal states

**目标：**
Connect `GenerationJobService` to the existing answer generator and image service so a job can run in the background, emit `chunk`, `done`, `job_error`, and `canceled`, and avoid marking canceled jobs as done.

**涉及文件：**
- Modify: `app/application/generation_job_service.py`
- Test: `tests/test_generation_job_service.py`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`tests/test_generation_job_service.py`
  - Add tests for successful generation, generator failure, image env fallback, and cancellation before completion:

```python
from unittest.mock import AsyncMock


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

        self.assertEqual(service.get_job_snapshot(job.id)["status"], "canceled")
```

  - 运行命令：`uv run pytest tests/test_generation_job_service.py -v`
  - 预期结果：new tests fail because execution methods and injected dependencies are not implemented.

- [ ] Step 2: 写最小实现
  - 文件：`app/application/generation_job_service.py`
  - Implement dependency injection:

```python
def __init__(
    self,
    retention_minutes: int = 30,
    max_jobs: int = 200,
    autostart: bool = True,
    answer_generator: DeepSeekAnswerGenerator | None = None,
    image_service: ImageGenerationService | None = None,
) -> None:
    self._answer_generator = answer_generator or DeepSeekAnswerGenerator()
    self._image_service = image_service or ImageGenerationService()
```

  - Implement `run_generate_one_job(job_id)` by copying the existing logic from `app/api/routes/stream.py`:
    - call `load_env_file()`
    - normalize platform with `normalize_platform`
    - build config with `get_workflow_config`
    - stream chunks from `generate_answer_stream`
    - append `chunk` events
    - generate images after full text
    - ignore `ValueError` containing `Missing required env: IMAGE_`
    - mark done with `item.model_dump(by_alias=True)`
    - mark error with `job_error` for other exceptions
  - Before appending chunks and before marking done, check whether current job status is `canceled`; if canceled, stop updating the job.

- [ ] Step 3: 运行测试
  - 命令：`uv run pytest tests/test_generation_job_service.py -v`
  - 预期结果：all service tests pass.

- [ ] Step 4: 重构
  - 文件：`app/application/generation_job_service.py`
  - Extract private helpers `_build_generation_config(payload)`, `_terminalize(job, status)`, and `_get_required_job(job_id)` to keep public methods short.

- [ ] Step 5: 再次验证
  - 命令：`uv run pytest tests/test_generation_job_service.py -v`
  - 预期结果：all service tests pass.

- [ ] Step 6: 提交
  - 提交信息：`feat: run generation jobs in background`

### Task 3: Standard SSE formatting and job routes

**目标：**
Expose reliable job endpoints with the project envelope, standard SSE `id/event/data`, replay from `Last-Event-ID` or query `lastEventId`, and cancellation.

**涉及文件：**
- Modify: `app/api/sse_utils.py`
- Create: `app/api/routes/generation_jobs.py`
- Modify: `app/server.py`
- Test: `tests/test_generation_job_routes.py`
- Test: `tests/test_generation_job_service.py`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`tests/test_generation_job_routes.py`
  - Add route tests using a FastAPI app with only the new router:

```python
from __future__ import annotations

import asyncio
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.generation_jobs import router, set_generation_job_service
from app.application.generation_job_service import GenerationJobService
from tests.test_generation_job_service import make_payload


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
        asyncio.run(service.append_event(job.id, "done", {"item": {"answer": "ab"}}))

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

        response = client.get(
            f"/api/workflow/generate-one/jobs/{job.id}/stream?lastEventId=0",
            headers={"Last-Event-ID": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("id: 2", response.text)
        self.assertNotIn("id: 1", response.text)

    def test_cancel_job_returns_canceled_snapshot(self) -> None:
        service = GenerationJobService(retention_minutes=30, max_jobs=10, autostart=False)
        client = make_client(service)
        job = asyncio.run(service.create_generate_one_job(make_payload()))

        response = client.delete(f"/api/workflow/generate-one/jobs/{job.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "canceled")
```

  - 运行命令：`uv run pytest tests/test_generation_job_routes.py -v`
  - 预期结果：fails because `app.api.routes.generation_jobs` does not exist.

- [ ] Step 2: 写最小实现
  - 文件：`app/api/sse_utils.py`
  - Add a new formatter without changing `sse_event(payload)`:

```python
def sse_named_event(event: str, data: dict, event_id: int | None = None) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"
```

  - 文件：`app/api/routes/generation_jobs.py`
  - Implement route module with:
    - module-level `_generation_job_service = GenerationJobService()`
    - `set_generation_job_service(service)` for tests
    - `POST /generate-one/jobs`
    - `GET /generate-one/jobs/{job_id}`
    - `GET /generate-one/jobs/{job_id}/stream`
    - `DELETE /generate-one/jobs/{job_id}`
  - Stream route rules:
    - parse `Last-Event-ID` first
    - fallback to query `lastEventId`
    - replay cached events with `sse_named_event`
    - for terminal jobs, close after replay
    - for running jobs, keep waiting on service notifications and send heartbeat at the service interval

  - 文件：`app/server.py`
  - Add:

```python
from .api.routes.generation_jobs import router as generation_jobs_router

app.include_router(generation_jobs_router)
```

- [ ] Step 3: 运行测试
  - 命令：`uv run pytest tests/test_generation_job_routes.py tests/test_generation_job_service.py -v`
  - 预期结果：route and service tests pass.

- [ ] Step 4: 重构
  - 文件：`app/api/routes/generation_jobs.py`
  - Extract `_parse_last_event_id(last_event_id_header, last_event_id_query)` and `_job_or_404(job_id)` for clarity.
  - Keep route functions thin: parse inputs, call service, wrap response.

- [ ] Step 5: 再次验证
  - 命令：`uv run pytest tests/test_generation_job_routes.py tests/test_generation_job_service.py -v`
  - 预期结果：all backend job tests pass.

- [ ] Step 6: 提交
  - 提交信息：`feat: expose generation job routes`

### Task 4: Legacy stream compatibility tests

**目标：**
Lock down the old stream protocol so the reliable job work does not break existing `fetch + ReadableStream` consumers.

**涉及文件：**
- Test: `tests/test_generation_job_routes.py`
- Modify only if needed: `app/api/routes/stream.py`
- Modify only if needed: `app/api/sse_utils.py`

**步骤：**

- [ ] Step 1: 写失败测试
  - 文件：`tests/test_generation_job_routes.py`
  - Add a compatibility test against existing `generate_one_stream`:

```python
from unittest.mock import AsyncMock, patch

from app.api.routes.stream import generate_one_stream


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
```

  - 运行命令：`uv run pytest tests/test_generation_job_routes.py::LegacyStreamCompatibilityTests -v`
  - 预期结果：passes if Task 3 kept compatibility; fails if the old formatter was changed.

- [ ] Step 2: 写最小实现
  - 文件：`app/api/sse_utils.py`
  - If compatibility failed, restore `sse_event(payload)` to this behavior:

```python
def sse_event(payload: dict) -> str:
    """将字典序列化为旧 SSE data 行格式。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
```

- [ ] Step 3: 运行测试
  - 命令：`uv run pytest tests/test_generation_job_routes.py::LegacyStreamCompatibilityTests -v`
  - 预期结果：compatibility test passes.

- [ ] Step 4: 重构
  - 文件：`app/api/sse_utils.py`
  - Keep both functions adjacent and document the split:
    - `sse_event`: legacy data-only protocol
    - `sse_named_event`: reliable job protocol

- [ ] Step 5: 再次验证
  - 命令：`uv run pytest tests/test_generation_job_routes.py tests/test_generation_job_service.py -v`
  - 预期结果：all backend job and compatibility tests pass.

- [ ] Step 6: 提交
  - 提交信息：`test: lock legacy stream protocol`

### Task 5: Frontend types and EventSource job client

**目标：**
Add typed job API functions and an EventSource client that supports `lastEventId`, duplicate filtering, `sessionStorage` persistence, recover timeout, and business event callbacks.

**涉及文件：**
- Modify: `frontend/src/types/workflow.ts`
- Modify: `frontend/src/features/workspace/workflow-api.ts`
- Create: `frontend/src/features/workspace/generation-job-client.ts`

**步骤：**

- [ ] Step 1: 写失败验证
  - 文件：`frontend/src/features/workspace/generation-job-client.ts`
  - Temporarily reference the new types and functions before defining them:

```typescript
import type { GenerationJobSnapshot, GenerationJobStatus } from "@/types/workflow";

export type GenerationJobClientProbe = {
  status: GenerationJobStatus;
  snapshot: GenerationJobSnapshot;
};
```

  - 运行命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck fails because `GenerationJobSnapshot` and `GenerationJobStatus` are not exported.

- [ ] Step 2: 写最小实现
  - 文件：`frontend/src/types/workflow.ts`
  - Add these types:

```typescript
export type GenerationJobStatus = "pending" | "running" | "done" | "error" | "canceled";

export type GenerationJobSnapshot = {
  jobId: string;
  kind: "generate_one";
  status: GenerationJobStatus;
  itemId: string;
  finalItem: QuestionItem | null;
  error: string | null;
  lastEventId: number;
  createdAt: string;
  updatedAt: string;
  expiresAt: string | null;
};

export type CreateGenerationJobResponse = {
  jobId: string;
  status: GenerationJobStatus;
};

export type GenerationJobSseEvent =
  | { id: number; event: "chunk"; data: { text: string } }
  | { id: number; event: "done"; data: { item: QuestionItem } }
  | { id: number; event: "job_error"; data: { message: string } }
  | { id: number; event: "canceled"; data: { message: string } };

export type GenerationUiStatus =
  | "idle"
  | "creating"
  | "generating"
  | "done"
  | "error"
  | "interrupted"
  | "canceled";
```

  - Update `GenerationStatus` to:

```typescript
export type GenerationStatus = "idle" | "creating" | "generating" | "done" | "error" | "interrupted" | "canceled";
```

  - 文件：`frontend/src/features/workspace/workflow-api.ts`
  - Add API functions:

```typescript
export function createGenerationJob(payload: GenerateOnePayload) {
  return apiPost<CreateGenerationJobResponse>("/api/workflow/generate-one/jobs", payload);
}

export function getGenerationJob(jobId: string) {
  return apiGet<GenerationJobSnapshot>(`/api/workflow/generate-one/jobs/${jobId}`);
}

export function cancelGenerationJob(jobId: string) {
  return apiDelete<{ jobId: string; status: "canceled" }>(`/api/workflow/generate-one/jobs/${jobId}`);
}
```

  - 文件：`frontend/src/features/workspace/generation-job-client.ts`
  - Replace the probe with:

```typescript
import type { GenerationJobSseEvent } from "@/types/workflow";

export type GenerationJobSubscription = {
  close: () => void;
};

export type GenerationJobCallbacks = {
  onChunk?: (text: string, eventId: number) => void;
  onDone?: (item: GenerationJobSseEvent & { event: "done" }) => void;
  onJobError?: (message: string, eventId: number) => void;
  onCanceled?: (message: string, eventId: number) => void;
  onRecovering?: () => void;
  onInterrupted?: (message: string) => void;
};

export function subscribeGenerationJob(
  jobId: string,
  lastEventId: number,
  callbacks: GenerationJobCallbacks,
  recoverTimeoutMs = 60_000,
): GenerationJobSubscription {
  let appliedLastEventId = lastEventId;
  let closed = false;
  let interruptedTimer: number | null = window.setTimeout(() => {
    if (!closed) callbacks.onInterrupted?.("生成连接恢复超时，请继续恢复或重新生成");
  }, recoverTimeoutMs);
  const source = new EventSource(`/api/workflow/generate-one/jobs/${jobId}/stream?lastEventId=${lastEventId}`);

  function clearInterruptedTimer() {
    if (interruptedTimer !== null) {
      window.clearTimeout(interruptedTimer);
      interruptedTimer = null;
    }
  }

  function applyEvent(eventName: GenerationJobSseEvent["event"], event: MessageEvent) {
    const eventId = Number(event.lastEventId);
    if (!Number.isFinite(eventId) || eventId <= appliedLastEventId) return;
    appliedLastEventId = eventId;
    clearInterruptedTimer();
    const data = JSON.parse(event.data);
    if (eventName === "chunk") callbacks.onChunk?.(data.text || "", eventId);
    if (eventName === "done") callbacks.onDone?.({ id: eventId, event: "done", data });
    if (eventName === "job_error") callbacks.onJobError?.(data.message || "生成失败", eventId);
    if (eventName === "canceled") callbacks.onCanceled?.(data.message || "生成已取消", eventId);
  }

  source.addEventListener("chunk", (event) => applyEvent("chunk", event as MessageEvent));
  source.addEventListener("done", (event) => applyEvent("done", event as MessageEvent));
  source.addEventListener("job_error", (event) => applyEvent("job_error", event as MessageEvent));
  source.addEventListener("canceled", (event) => applyEvent("canceled", event as MessageEvent));
  source.onerror = () => callbacks.onRecovering?.();

  return {
    close: () => {
      closed = true;
      clearInterruptedTimer();
      source.close();
    },
  };
}
```

  - Add persistence helpers in the same file:

```typescript
const STORAGE_KEY = "workbench:generation-job";

export type StoredGenerationJob = {
  jobId: string;
  itemId: string;
  lastEventId: number;
  streamingAnswer: string;
};

export function saveStoredGenerationJob(value: StoredGenerationJob) {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export function readStoredGenerationJob(): StoredGenerationJob | null {
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredGenerationJob;
  } catch {
    window.sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function clearStoredGenerationJob() {
  window.sessionStorage.removeItem(STORAGE_KEY);
}
```

- [ ] Step 3: 运行测试
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck passes.

- [ ] Step 4: 重构
  - 文件：`frontend/src/features/workspace/generation-job-client.ts`
  - Move URL construction into `buildGenerationJobStreamUrl(jobId, lastEventId)` and export it for readability.
  - Keep callback names aligned with SSE events: `onJobError`, not `onError`.

- [ ] Step 5: 再次验证
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck passes.

- [ ] Step 6: 提交
  - 提交信息：`feat: add generation job client`

### Task 6: Workbench store generation state

**目标：**
Keep streaming preview, final answer, draft answer, job id, and last event id separate in Zustand so token-level updates do not write to `item.answer`.

**涉及文件：**
- Modify: `frontend/src/types/workflow.ts`
- Modify: `frontend/src/store/workbench-store.ts`

**步骤：**

- [ ] Step 1: 写失败验证
  - 文件：`frontend/src/store/workbench-store.ts`
  - Temporarily use new action names in the store type before implementing them:

```typescript
  startItemGenerationJob: (id: string, jobId: string) => void;
  appendItemStreamingAnswer: (id: string, text: string, eventId: number) => void;
  finishItemGenerationJob: (id: string, item: WorkbenchItem, eventId: number) => void;
```

  - 运行命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck fails because the Zustand initializer does not implement these required actions.

- [ ] Step 2: 写最小实现
  - 文件：`frontend/src/types/workflow.ts`
  - Add to `WorkbenchItem`:

```typescript
  generationJob?: {
    jobId: string;
    status: GenerationUiStatus;
    lastEventId: number;
    streamingAnswer: string;
    finalAnswer: string;
    draftAnswer: string;
    error: string | null;
  };
```

  - 文件：`frontend/src/store/workbench-store.ts`
  - Add actions:

```typescript
  startItemGenerationJob: (id, jobId) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              generationStatus: "generating",
              generationError: undefined,
              generationJob: {
                jobId,
                status: "generating",
                lastEventId: 0,
                streamingAnswer: "",
                finalAnswer: "",
                draftAnswer: i.answer || "",
                error: null,
              },
            }
          : i,
      ),
    })),

  appendItemStreamingAnswer: (id, text, eventId) =>
    set((state) => ({
      items: state.items.map((i) => {
        if (i.id !== id || !i.generationJob || eventId <= i.generationJob.lastEventId) return i;
        return {
          ...i,
          generationJob: {
            ...i.generationJob,
            lastEventId: eventId,
            streamingAnswer: i.generationJob.streamingAnswer + text,
          },
        };
      }),
    })),

  finishItemGenerationJob: (id, item, eventId) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.id === id
          ? {
              ...i,
              ...item,
              addedAt: i.addedAt,
              sourcePlatform: i.sourcePlatform,
              sourceTopic: i.sourceTopic,
              promptConfig: i.promptConfig,
              generationStatus: "done",
              generationError: undefined,
              generationJob: {
                ...(i.generationJob ?? {
                  jobId: "",
                  streamingAnswer: "",
                  error: null,
                }),
                status: "done",
                lastEventId: eventId,
                finalAnswer: item.answer || "",
                draftAnswer: item.answer || "",
              },
            }
          : i,
      ),
    })),
```

  - Add matching actions for `failItemGenerationJob`, `interruptItemGenerationJob`, `cancelItemGenerationJob`, and `restoreItemGenerationJob`.
  - Update `setItemGenerationStatus` so `canceled` clears `generationError` like `done`.

- [ ] Step 3: 运行测试
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck passes.

- [ ] Step 4: 重构
  - 文件：`frontend/src/store/workbench-store.ts`
  - Extract `mergeWorkbenchItem(current, next)` helper to preserve `addedAt`, `sourcePlatform`, `sourceTopic`, and `promptConfig` in one place.

- [ ] Step 5: 再次验证
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck passes.

- [ ] Step 6: 提交
  - 提交信息：`feat: separate workbench generation state`

### Task 7: Workbench UI migration to reliable job flow

**目标：**
Replace the single-answer legacy stream call in `WorkbenchAnswerPanel` with create job + EventSource subscription, while rendering preview during generation and `MarkdownEditor` only after completion.

**涉及文件：**
- Modify: `frontend/src/features/workbench/workbench-answer-panel.tsx`
- Modify: `frontend/src/features/workspace/workflow-api.ts`
- Modify: `frontend/src/features/workspace/generation-job-client.ts`
- Modify: `frontend/src/store/workbench-store.ts`

**步骤：**

- [ ] Step 1: 写失败验证
  - 文件：`frontend/src/features/workbench/workbench-answer-panel.tsx`
  - Replace the import of `streamGenerateOneAnswer` with the new APIs before wiring them:

```typescript
import {
  clearStoredGenerationJob,
  readStoredGenerationJob,
  saveStoredGenerationJob,
  subscribeGenerationJob,
  type GenerationJobSubscription,
} from "@/features/workspace/generation-job-client";
import { createGenerationJob, getGenerationJob } from "@/features/workspace/workflow-api";
```

  - 运行命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck fails if Task 5 exports are missing or store actions are not wired.

- [ ] Step 2: 写最小实现
  - 文件：`frontend/src/features/workbench/workbench-answer-panel.tsx`
  - Replace `useMutation` legacy stream logic with:
    - `useRef<GenerationJobSubscription | null>(null)`
    - `useEffect` cleanup that closes active subscription on unmount
    - `startGeneration(target)` async function that:
      - calls `createGenerationJob`
      - calls `startItemGenerationJob(target.id, jobId)`
      - saves `{ jobId, itemId: target.id, lastEventId: 0, streamingAnswer: "" }`
      - subscribes with `subscribeGenerationJob`
      - appends chunks into `generationJob.streamingAnswer`
      - finishes with `finishItemGenerationJob(target.id, item, eventId)`
      - handles `job_error`, `canceled`, `interrupted`
  - Use this render rule:

```tsx
const generationJob = item.generationJob;
const isGenerating = item.generationStatus === "creating" || item.generationStatus === "generating";
const preview = generationJob?.streamingAnswer || "";

{isGenerating ? (
  <div className="min-h-[320px] rounded-md border border-blue-300 bg-white px-3 py-3 text-[14px] leading-7 text-slate-800">
    {preview.trim() ? (
      <div className="whitespace-pre-wrap break-words">{preview}</div>
    ) : (
      <div className="text-slate-400">AI 正在生成回答...</div>
    )}
  </div>
) : (
  <MarkdownEditor
    className="min-h-[320px] rounded-md border border-slate-200 bg-white transition-colors"
    placeholder="点击 AI 生成 按钮自动撰写，或直接手工编辑内容。"
    value={item.answer || ""}
    onChange={(v) => updateItemAnswer(item.id, v)}
  />
)}
```

  - Add a restore effect:
    - read `readStoredGenerationJob()`
    - call `getGenerationJob(jobId)`
    - if status is `done` and `finalItem` exists, finish immediately
    - if status is `pending` or `running`, restore local streaming answer and subscribe with stored `lastEventId`
    - if request fails, clear storage and set item interrupted only when item still exists

- [ ] Step 3: 运行测试
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck passes.

- [ ] Step 4: 重构
  - 文件：`frontend/src/features/workbench/workbench-answer-panel.tsx`
  - Extract small local helpers:
    - `buildGenerateOnePayload(target)`
    - `closeCurrentSubscription()`
    - `subscribeToJob(target, jobId, lastEventId)`
  - Keep UI markup readable and avoid nested cards.

- [ ] Step 5: 再次验证
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck passes.

- [ ] Step 6: 提交
  - 提交信息：`feat: migrate workbench generation to jobs`

### Task 8: End-to-end backend and frontend verification

**目标：**
Run all required verification, document manual checks, and ensure the implementation satisfies every acceptance criterion without touching unrelated features.

**涉及文件：**
- Modify if needed: `docs/plans/plan-reliable-sse-generation.md`
- Verify: backend tests, frontend typecheck, manual app flow

**步骤：**

- [ ] Step 1: 运行后端 job 测试
  - 命令：`uv run pytest tests/test_generation_job_service.py tests/test_generation_job_routes.py -v`
  - 预期结果：all tests pass.

- [ ] Step 2: 运行相关回归测试
  - 命令：`uv run pytest tests/test_answer_service.py tests/test_models_session_payload.py -v`
  - 预期结果：all tests pass.

- [ ] Step 3: 运行前端类型检查
  - 命令：`cd frontend && bun run typecheck`
  - 预期结果：typecheck passes with no TypeScript errors.

- [ ] Step 4: 可选构建验证
  - 命令：`cd frontend && bun run build`
  - 预期结果：Vite build succeeds.

- [ ] Step 5: 手工验证正常生成
  - 启动后端：`uv run python -m app.server`
  - 启动前端：`cd frontend && bun run dev`
  - 操作：打开 `/workbench`，导入或选择一个问题，点击“AI 生成”。
  - 预期结果：先显示只读预览，收到 `done` 后显示编辑器，最终回答等于服务端 `done.item.answer`。

- [ ] Step 6: 手工验证恢复路径
  - 操作：生成中用 DevTools 切到 offline，再恢复 online。
  - 预期结果：前端显示恢复提示，恢复后缺失 chunk 被补发，预览文本不重复。
  - 操作：生成中刷新页面。
  - 预期结果：前端读取 `sessionStorage`，查询 job，并恢复订阅或直接显示最终结果。

- [ ] Step 7: 手工验证失败和兼容路径
  - 操作：临时让后端生成器抛出异常或使用测试替身触发 `job_error`。
  - 预期结果：前端显示错误，不把预览保存为最终回答。
  - 操作：调用旧 `streamGenerateOneAnswer` 相关页面或后端测试。
  - 预期结果：旧 `data: {"type": ...}` 协议仍可用。

- [ ] Step 8: 最终提交
  - 提交信息：`chore: verify reliable generation flow`

## TDD 执行步骤（TDD Steps）

每个任务遵循同一节奏：

1. 先写失败测试或失败类型检查入口。
2. 运行指定命令，确认失败原因是目标能力尚未实现。
3. 写最小实现，不加入 specs 之外的功能。
4. 运行指定命令，确认通过。
5. 在测试通过后重构。
6. 再次运行指定命令。
7. 按任务提交。

前端目前没有 Vitest/RTL 配置。本计划不新增测试框架；前端行为通过 TypeScript 类型检查、后端集成测试和手工端到端验证覆盖。若执行阶段决定引入前端测试框架，必须先更新 specs 或获得用户确认。

## 验证命令（Verification Commands）

- `uv run pytest tests/test_generation_job_service.py -v`
  - 预期结果：job service 单元测试通过。
- `uv run pytest tests/test_generation_job_routes.py -v`
  - 预期结果：job route、SSE replay 和 legacy compatibility 测试通过。
- `uv run pytest tests/test_generation_job_service.py tests/test_generation_job_routes.py tests/test_answer_service.py tests/test_models_session_payload.py -v`
  - 预期结果：相关后端测试通过。
- `cd frontend && bun run typecheck`
  - 预期结果：TypeScript 无错误。
- `cd frontend && bun run build`
  - 预期结果：Vite build 成功。

## 提交计划（Commit Plan）

- Task 1: `feat: add generation job event store`
- Task 2: `feat: run generation jobs in background`
- Task 3: `feat: expose generation job routes`
- Task 4: `test: lock legacy stream protocol`
- Task 5: `feat: add generation job client`
- Task 6: `feat: separate workbench generation state`
- Task 7: `feat: migrate workbench generation to jobs`
- Task 8: `chore: verify reliable generation flow`

每个任务完成并通过对应验证后提交。若工作区存在用户未提交改动，提交前只 stage 本任务涉及文件。

## 风险与回滚（Risks and Rollback）

- 风险：后台 job service 使用内存缓存，服务重启会丢 job。
  - 回滚：保留旧 `streamGenerateOneAnswer` 和旧后端 `/generate-one/stream`，必要时前端恢复旧调用。
- 风险：EventSource 自动重连和页面刷新恢复路径容易重复追加 chunk。
  - 回滚：使用 `lastEventId` 去重；若异常，先禁用刷新恢复，只保留自动重连。
- 风险：图片生成在文本完成后延迟 `done`。
  - 回滚：保持预览状态直到 `done`，不提前进入编辑器。
- 风险：前端 store 状态变复杂，可能影响问题列表状态筛选。
  - 回滚：`generationStatus` 保持兼容字段，筛选仍以 `generationStatus` 和最终 `answer` 为准。
- 风险：新标准 SSE formatter 误改旧 formatter。
  - 回滚：Task 4 的 legacy compatibility test 会拦截；恢复 `sse_event(payload)` data-only 行为。

## 完成标准（Definition of Done）

- `docs/specs/feature-reliable-sse-generation.md` 的 R1-R25 和 AC1-AC10 均有实现或验证覆盖。
- 新 job routes 返回统一 envelope，SSE stream 使用标准 `id/event/data`。
- 断线重连和刷新恢复使用 `Last-Event-ID` 或 `?lastEventId=` 补发，不重复追加文本。
- 工作台生成中不挂载 `MarkdownEditor`，完成后才以 `done.item.answer` 初始化编辑器。
- 旧流式接口和 `frontend/src/lib/sse.ts` 兼容路径仍可用。
- 后端相关 pytest 通过。
- `cd frontend && bun run typecheck` 通过。
- 手工端到端验证记录正常生成、断网恢复、刷新恢复、失败事件和旧接口兼容。
- 用户确认实现结果。

## Self-Review

- Spec coverage: R1-R10 covered by Tasks 1-3; R11-R17 covered by Tasks 3-4; R18-R25 covered by Tasks 5-7; AC1-AC10 covered by Tasks 3-8.
- Placeholder scan: no placeholder sections or deferred requirements are intentionally left in this plan.
- Type consistency: backend uses `job_error`; frontend callbacks use `onJobError`; query parameter is consistently `lastEventId`; final item field is consistently `finalItem`.
