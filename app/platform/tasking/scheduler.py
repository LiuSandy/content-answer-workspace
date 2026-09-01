from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .exceptions import SchedulerNotRunningError
from .models import SchedulerState, Task
from .notifier import EventTaskNotifier
from .pool import WorkerPool
from .ports import TaskNotifier, TaskQueue
from .recovery import StaleTaskRecovery
from .registry import TaskHandlerRegistry
from .retry import ExponentialBackoffRetryPolicy, RetryPolicy
from .worker import WorkerConfig


@dataclass(frozen=True, slots=True)
class TaskSchedulerConfig:
    worker_count: int = 2
    lease_seconds: float = 60.0
    idle_wait_seconds: float = 5.0
    task_timeout_seconds: float | None = None
    recovery_interval_seconds: float = 30.0
    shutdown_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.worker_count < 1:
            raise ValueError("worker_count must be at least 1")
        positive = (
            self.lease_seconds,
            self.idle_wait_seconds,
            self.recovery_interval_seconds,
            self.shutdown_timeout_seconds,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("scheduler timeouts must be positive")
        if self.task_timeout_seconds is not None and self.task_timeout_seconds <= 0:
            raise ValueError("task timeout must be positive")


class TaskScheduler:
    """通用调度器，只负责任务提交和核心组件的生命周期编排。"""

    def __init__(
        self,
        queue: TaskQueue,
        handlers: TaskHandlerRegistry,
        config: TaskSchedulerConfig | None = None,
        retry_policy: RetryPolicy | None = None,
        notifier: TaskNotifier | None = None,
        name: str | None = None,
    ) -> None:
        self.queue = queue
        self.handlers = handlers
        self.config = config or TaskSchedulerConfig()
        self.retry_policy = retry_policy or ExponentialBackoffRetryPolicy()
        self.notifier = notifier or EventTaskNotifier()
        self._stop = asyncio.Event()
        self._state = SchedulerState.STOPPED
        self._lifecycle_lock = asyncio.Lock()

        worker_config = WorkerConfig(
            lease_seconds=self.config.lease_seconds,
            idle_wait_seconds=self.config.idle_wait_seconds,
            task_timeout_seconds=self.config.task_timeout_seconds,
        )
        self._pool = WorkerPool(
            worker_count=self.config.worker_count,
            queue=self.queue,
            notifier=self.notifier,
            registry=self.handlers,
            retry_policy=self.retry_policy,
            worker_config=worker_config,
            name=name,
        )
        self._recovery = StaleTaskRecovery(
            queue=self.queue,
            notifier=self.notifier,
            interval_seconds=self.config.recovery_interval_seconds,
        )
        self._recovery_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> SchedulerState:
        return self._state

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._state == SchedulerState.RUNNING:
                return
            if self._state not in {SchedulerState.STOPPED, SchedulerState.FAILED}:
                raise RuntimeError(f"Cannot start scheduler while state is {self._state}")
            self._state = SchedulerState.STARTING
            self._stop.clear()
            self._recovery.reset()
            try:
                await self.queue.start()
                await self.notifier.start()
                await self._pool.start()
                self._recovery_task = asyncio.create_task(
                    self._recovery.run(),
                    name="task-stale-recovery",
                )
                self._state = SchedulerState.RUNNING
                await self.notifier.notify()
            except Exception:
                self._state = SchedulerState.FAILED
                await self._cleanup_failed_start()
                raise

    async def submit(self, task: Task) -> None:
        async with self._lifecycle_lock:
            if self._state != SchedulerState.RUNNING:
                raise SchedulerNotRunningError(
                    f"Task scheduler is not running: {self._state}"
                )
            await self.queue.submit(task)
            await self.notifier.notify()

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            if self._state == SchedulerState.STOPPED:
                return
            if self._state == SchedulerState.DRAINING:
                return
            self._state = SchedulerState.DRAINING
            self._stop.set()
            await self._recovery.stop()
            await self._pool.stop_claiming()

        if self._recovery_task:
            await asyncio.gather(self._recovery_task, return_exceptions=True)
            self._recovery_task = None

        drained = await self._pool.drain(self.config.shutdown_timeout_seconds)
        if not drained:
            await self._pool.force_stop()

        await self.notifier.close()
        await self.queue.close()

        async with self._lifecycle_lock:
            self._state = SchedulerState.STOPPED

    async def _cleanup_failed_start(self) -> None:
        await self._recovery.stop()
        await self._pool.force_stop()
        await self.notifier.close()
        await self.queue.close()

    async def __aenter__(self) -> TaskScheduler:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()
