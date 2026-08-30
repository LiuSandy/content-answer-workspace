from __future__ import annotations

import asyncio
import logging

from .models import utcnow
from .ports import TaskNotifier, TaskQueue

logger = logging.getLogger(__name__)


class StaleTaskRecovery:
    """定期恢复租约过期的任务。"""

    def __init__(
        self,
        queue: TaskQueue,
        notifier: TaskNotifier,
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("recovery interval must be positive")
        self.queue = queue
        self.notifier = notifier
        self.interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def reset(self) -> None:
        self._stop.clear()

    async def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                recovered = await self.queue.recover_stale(utcnow())
                if recovered:
                    logger.info("Recovered %d stale tasks", recovered)
                    await self.notifier.notify()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Task recovery cycle failed")

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass
