from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .exceptions import LeaseLostError, QueueClosedError, TaskTimeoutError
from .models import TaskLease, utcnow
from .ports import TaskNotifier, TaskQueue
from .registry import TaskHandlerRegistry
from .retry import RetryPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    lease_seconds: float = 60.0
    idle_wait_seconds: float = 5.0
    task_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.lease_seconds <= 0 or self.idle_wait_seconds <= 0:
            raise ValueError("worker lease and idle wait must be positive")
        if self.task_timeout_seconds is not None and self.task_timeout_seconds <= 0:
            raise ValueError("task timeout must be positive")


class Worker:
    """单个消费者循环；只处理任务生命周期，不包含具体业务。"""

    def __init__(
        self,
        owner: str,
        queue: TaskQueue,
        notifier: TaskNotifier,
        registry: TaskHandlerRegistry,
        retry_policy: RetryPolicy,
        config: WorkerConfig,
    ) -> None:
        self.owner = owner
        self.queue = queue
        self.notifier = notifier
        self.registry = registry
        self.retry_policy = retry_policy
        self.config = config
        self._stop_claiming = asyncio.Event()
        self._in_flight: TaskLease | None = None

    @property
    def in_flight(self) -> TaskLease | None:
        return self._in_flight

    def stop_claiming(self) -> None:
        self._stop_claiming.set()

    async def run(self) -> None:
        while not self._stop_claiming.is_set():
            generation = self.notifier.generation
            try:
                lease = await self.queue.claim(self.owner, self.config.lease_seconds)
            except QueueClosedError:
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker %s failed to claim a task", self.owner)
                await self.notifier.wait(generation, self.config.idle_wait_seconds)
                continue

            if lease is None:
                await self.notifier.wait(generation, self.config.idle_wait_seconds)
                continue

            try:
                await self._execute(lease)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 队列状态转换失败时保留租约，由恢复循环在租约过期后重新入队。
                logger.exception("Worker %s failed to finalize task %s", self.owner, lease.task.id)

    async def _execute(self, lease: TaskLease) -> None:
        self._in_flight = lease
        try:
            await self._run_handler_with_heartbeat(lease)
        except asyncio.CancelledError:
            await self._release_current_lease()
            raise
        except LeaseLostError:
            logger.warning("Worker %s lost lease for task %s", self.owner, lease.task.id)
        except Exception as error:
            current = self._in_flight or lease
            decision = self.retry_policy.decide(current.task, error)
            if decision.should_retry and decision.delay is not None:
                await self.queue.retry(
                    current,
                    str(error),
                    utcnow() + decision.delay,
                )
            else:
                await self.queue.fail(current, str(error))
        else:
            await self.queue.complete(self._in_flight or lease)
        finally:
            self._in_flight = None

    async def _run_handler_with_heartbeat(self, lease: TaskLease) -> None:
        handler = self.registry.resolve(lease.task.task_type)
        handler_task = asyncio.create_task(
            self._invoke_handler(handler, lease),
            name=f"task-handler-{lease.task.id}",
        )
        heartbeat_task = asyncio.create_task(
            self._heartbeat(lease),
            name=f"lease-heartbeat-{lease.task.id}",
        )
        try:
            done, _ = await asyncio.wait(
                {handler_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                error = heartbeat_task.exception()
                if error is None:
                    raise LeaseLostError(f"Heartbeat stopped unexpectedly: {lease.task.id}")
                raise error
            await handler_task
        finally:
            for task in (handler_task, heartbeat_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(handler_task, heartbeat_task, return_exceptions=True)

    async def _invoke_handler(self, handler, lease: TaskLease) -> None:
        if self.config.task_timeout_seconds is None:
            await handler.handle(lease.task)
            return
        try:
            async with asyncio.timeout(self.config.task_timeout_seconds):
                await handler.handle(lease.task)
        except TimeoutError as exc:
            raise TaskTimeoutError(
                f"Task exceeded {self.config.task_timeout_seconds} seconds"
            ) from exc

    async def _heartbeat(self, lease: TaskLease) -> None:
        interval = max(0.1, self.config.lease_seconds / 3)
        current = lease
        while True:
            await asyncio.sleep(interval)
            current = await self.queue.renew(current, self.config.lease_seconds)
            self._in_flight = current

    async def _release_current_lease(self) -> None:
        if self._in_flight is None:
            return
        try:
            await self.queue.release(self._in_flight)
            await self.notifier.notify()
        except LeaseLostError:
            logger.warning(
                "Worker %s could not release expired lease for task %s",
                self.owner,
                self._in_flight.task.id,
            )
