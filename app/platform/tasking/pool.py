from __future__ import annotations

import asyncio
import logging
import socket
import uuid

from .ports import TaskNotifier, TaskQueue
from .registry import TaskHandlerRegistry
from .retry import RetryPolicy
from .worker import Worker, WorkerConfig

logger = logging.getLogger(__name__)


class WorkerPool:
    """创建和管理一组相互独立的 Worker。"""

    def __init__(
        self,
        worker_count: int,
        queue: TaskQueue,
        notifier: TaskNotifier,
        registry: TaskHandlerRegistry,
        retry_policy: RetryPolicy,
        worker_config: WorkerConfig,
        name: str | None = None,
    ) -> None:
        if worker_count < 1:
            raise ValueError("worker_count must be at least 1")
        self.worker_count = worker_count
        self.queue = queue
        self.notifier = notifier
        self.registry = registry
        self.retry_policy = retry_policy
        self.worker_config = worker_config
        self.name = name or socket.gethostname()
        self._workers: list[Worker] = []
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def workers(self) -> tuple[Worker, ...]:
        return tuple(self._workers)

    async def start(self) -> None:
        if self._tasks:
            return
        instance = uuid.uuid4().hex[:10]
        self._workers = [
            Worker(
                owner=f"{self.name}:{instance}:{index}",
                queue=self.queue,
                notifier=self.notifier,
                registry=self.registry,
                retry_policy=self.retry_policy,
                config=self.worker_config,
            )
            for index in range(self.worker_count)
        ]
        self._tasks = [
            asyncio.create_task(worker.run(), name=f"{self.name}-worker-{index}")
            for index, worker in enumerate(self._workers)
        ]

    async def stop_claiming(self) -> None:
        for worker in self._workers:
            worker.stop_claiming()
        await self.notifier.notify()

    async def drain(self, timeout: float) -> bool:
        if not self._tasks:
            return True
        _, pending = await asyncio.wait(self._tasks, timeout=timeout)
        if pending:
            return False
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._workers.clear()
        return True

    async def force_stop(self) -> None:
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            results = await asyncio.gather(*self._tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.error("Worker stopped with error: %r", result)
        self._tasks.clear()
        self._workers.clear()
