from __future__ import annotations

import asyncio


class EventTaskNotifier:
    """单进程通知器，使用 generation 避免 Event.clear() 丢失并发通知。"""

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._generation = 0
        self._closed = False

    @property
    def generation(self) -> int:
        return self._generation

    async def start(self) -> None:
        self._closed = False
        self._event.clear()

    async def notify(self) -> None:
        if self._closed:
            return
        self._generation += 1
        self._event.set()

    async def wait(self, after_generation: int, timeout: float) -> None:
        if self._closed or self._generation != after_generation:
            return
        self._event.clear()
        if self._generation != after_generation:
            return
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except TimeoutError:
            pass

    async def close(self) -> None:
        self._closed = True
        self._generation += 1
        self._event.set()
