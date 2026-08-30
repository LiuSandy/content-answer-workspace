from __future__ import annotations

import asyncio

import pytest

from app.infrastructure.worker import (
    ExponentialBackoffRetryPolicy,
    InMemoryTaskQueue,
    LeaseLostError,
    SchedulerNotRunningError,
    Task,
    TaskHandlerRegistry,
    TaskScheduler,
    TaskSchedulerConfig,
    TaskStatus,
)


async def wait_for_status(
    queue: InMemoryTaskQueue,
    task: Task,
    status: TaskStatus,
    timeout: float = 1.0,
) -> None:
    async with asyncio.timeout(timeout):
        while True:
            stored = await queue.get(task.id)
            if stored and stored.status == status:
                return
            await asyncio.sleep(0.005)


def make_scheduler(
    queue: InMemoryTaskQueue,
    registry: TaskHandlerRegistry,
    *,
    worker_count: int = 2,
    shutdown_timeout: float = 1.0,
) -> TaskScheduler:
    return TaskScheduler(
        queue=queue,
        handlers=registry,
        config=TaskSchedulerConfig(
            worker_count=worker_count,
            lease_seconds=0.3,
            idle_wait_seconds=0.02,
            recovery_interval_seconds=0.02,
            shutdown_timeout_seconds=shutdown_timeout,
        ),
        retry_policy=ExponentialBackoffRetryPolicy(base_delay=0, max_delay=0),
        name="test",
    )


@pytest.mark.asyncio
async def test_scheduler_processes_each_task_once_with_multiple_workers():
    queue = InMemoryTaskQueue()
    registry = TaskHandlerRegistry()
    processed: list[str] = []

    class Handler:
        async def handle(self, task: Task) -> None:
            processed.append(str(task.id))
            await asyncio.sleep(0)

    registry.register("example", Handler())
    scheduler = make_scheduler(queue, registry, worker_count=3)
    tasks = [Task("example", {"index": index}) for index in range(20)]

    await scheduler.start()
    try:
        for task in tasks:
            await scheduler.submit(task)
        for task in tasks:
            await wait_for_status(queue, task, TaskStatus.SUCCEEDED)
    finally:
        await scheduler.stop()

    assert len(processed) == len(tasks)
    assert len(set(processed)) == len(tasks)


@pytest.mark.asyncio
async def test_retryable_task_is_retried_then_succeeds():
    queue = InMemoryTaskQueue()
    registry = TaskHandlerRegistry()
    calls = 0

    class FlakyHandler:
        async def handle(self, task: Task) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary")

    registry.register("flaky", FlakyHandler())
    scheduler = make_scheduler(queue, registry, worker_count=1)
    task = Task("flaky", {}, max_attempts=2)

    await scheduler.start()
    try:
        await scheduler.submit(task)
        await wait_for_status(queue, task, TaskStatus.SUCCEEDED)
    finally:
        await scheduler.stop()

    assert calls == 2
    assert task.attempt == 2


@pytest.mark.asyncio
async def test_unknown_handler_fails_without_retry():
    queue = InMemoryTaskQueue()
    scheduler = make_scheduler(queue, TaskHandlerRegistry(), worker_count=1)
    task = Task("missing", {}, max_attempts=5)

    await scheduler.start()
    try:
        await scheduler.submit(task)
        await wait_for_status(queue, task, TaskStatus.FAILED)
    finally:
        await scheduler.stop()

    assert task.attempt == 1
    assert "No handler registered" in (task.last_error or "")


@pytest.mark.asyncio
async def test_graceful_stop_waits_for_in_flight_task():
    queue = InMemoryTaskQueue()
    registry = TaskHandlerRegistry()
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingHandler:
        async def handle(self, task: Task) -> None:
            started.set()
            await release.wait()

    registry.register("blocking", BlockingHandler())
    scheduler = make_scheduler(queue, registry, worker_count=1, shutdown_timeout=1.0)
    task = Task("blocking", {})

    await scheduler.start()
    await scheduler.submit(task)
    await asyncio.wait_for(started.wait(), timeout=1)

    stop_task = asyncio.create_task(scheduler.stop())
    await asyncio.sleep(0.02)
    assert not stop_task.done()

    release.set()
    await asyncio.wait_for(stop_task, timeout=1)
    assert task.status == TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_forced_stop_releases_in_flight_task():
    queue = InMemoryTaskQueue()
    registry = TaskHandlerRegistry()
    started = asyncio.Event()

    class NeverEndingHandler:
        async def handle(self, task: Task) -> None:
            started.set()
            await asyncio.Event().wait()

    registry.register("blocking", NeverEndingHandler())
    scheduler = make_scheduler(queue, registry, worker_count=1, shutdown_timeout=0.03)
    task = Task("blocking", {})

    await scheduler.start()
    await scheduler.submit(task)
    await asyncio.wait_for(started.wait(), timeout=1)
    await scheduler.stop()

    assert task.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_stale_lease_token_cannot_complete_reclaimed_task():
    queue = InMemoryTaskQueue()
    await queue.start()
    task = Task("example", {})
    await queue.submit(task)

    first = await queue.claim("worker-a", lease_seconds=0.01)
    assert first is not None
    await asyncio.sleep(0.02)
    assert await queue.recover_stale(first.expires_at) == 1

    second = await queue.claim("worker-b", lease_seconds=1)
    assert second is not None
    assert first.token != second.token

    with pytest.raises(LeaseLostError):
        await queue.complete(first)

    await queue.complete(second)
    assert task.status == TaskStatus.SUCCEEDED
    await queue.close()


@pytest.mark.asyncio
async def test_submit_requires_running_scheduler():
    scheduler = make_scheduler(InMemoryTaskQueue(), TaskHandlerRegistry())

    with pytest.raises(SchedulerNotRunningError):
        await scheduler.submit(Task("example", {}))
