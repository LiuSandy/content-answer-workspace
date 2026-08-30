from __future__ import annotations

import asyncio
import heapq
from collections import deque
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from ..exceptions import DuplicateTaskError, LeaseLostError, QueueClosedError
from ..models import Task, TaskLease, TaskStatus, utcnow


class InMemoryTaskQueue:
    """单进程参考队列，提供与持久化队列一致的状态和租约语义。"""

    def __init__(self, max_pending: int = 0, terminal_history_limit: int = 1000) -> None:
        if max_pending < 0 or terminal_history_limit < 0:
            raise ValueError("queue limits must not be negative")
        self.max_pending = max_pending
        self.terminal_history_limit = terminal_history_limit
        self._tasks: dict[UUID, Task] = {}
        self._idempotency_keys: dict[str, UUID] = {}
        self._pending: deque[UUID] = deque()
        self._retry_heap: list[tuple[float, int, UUID]] = []
        self._leases: dict[UUID, TaskLease] = {}
        self._terminal: deque[UUID] = deque()
        self._sequence = 0
        self._closed = True
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            self._closed = False

    async def submit(self, task: Task) -> None:
        async with self._lock:
            self._ensure_open()
            if task.id in self._tasks:
                raise DuplicateTaskError(f"Task already exists: {task.id}")
            if task.idempotency_key and task.idempotency_key in self._idempotency_keys:
                existing = self._idempotency_keys[task.idempotency_key]
                raise DuplicateTaskError(f"Idempotency key already exists for task: {existing}")
            if self.max_pending and len(self._pending) >= self.max_pending:
                raise asyncio.QueueFull
            task.status = TaskStatus.PENDING
            task.retry_at = None
            self._tasks[task.id] = task
            if task.idempotency_key:
                self._idempotency_keys[task.idempotency_key] = task.id
            self._pending.append(task.id)

    async def claim(self, owner: str, lease_seconds: float) -> TaskLease | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        async with self._lock:
            self._ensure_open()
            self._promote_due_retries(utcnow())
            while self._pending:
                task_id = self._pending.popleft()
                task = self._tasks.get(task_id)
                if task is None or task.status != TaskStatus.PENDING:
                    continue
                now = utcnow()
                task.attempt += 1
                task.status = TaskStatus.RUNNING
                task.started_at = task.started_at or now
                lease = TaskLease(
                    task=task,
                    owner=owner,
                    token=uuid4(),
                    expires_at=now + timedelta(seconds=lease_seconds),
                )
                self._leases[task.id] = lease
                return lease
            return None

    async def renew(self, lease: TaskLease, lease_seconds: float) -> TaskLease:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        async with self._lock:
            current = self._require_lease(lease, reject_expired=True)
            renewed = TaskLease(
                task=current.task,
                owner=current.owner,
                token=current.token,
                expires_at=utcnow() + timedelta(seconds=lease_seconds),
            )
            self._leases[lease.task.id] = renewed
            return renewed

    async def complete(self, lease: TaskLease) -> None:
        async with self._lock:
            current = self._require_lease(lease)
            task = current.task
            task.status = TaskStatus.SUCCEEDED
            task.retry_at = None
            task.last_error = None
            task.completed_at = utcnow()
            self._leases.pop(task.id, None)
            self._record_terminal(task.id)

    async def retry(self, lease: TaskLease, error: str, retry_at: datetime) -> None:
        async with self._lock:
            current = self._require_lease(lease)
            task = current.task
            task.status = TaskStatus.RETRY_WAIT
            task.last_error = error
            task.retry_at = retry_at
            self._leases.pop(task.id, None)
            self._sequence += 1
            heapq.heappush(self._retry_heap, (retry_at.timestamp(), self._sequence, task.id))

    async def fail(self, lease: TaskLease, error: str) -> None:
        async with self._lock:
            current = self._require_lease(lease)
            task = current.task
            task.status = TaskStatus.FAILED
            task.last_error = error
            task.retry_at = None
            task.completed_at = utcnow()
            self._leases.pop(task.id, None)
            self._record_terminal(task.id)

    async def release(self, lease: TaskLease) -> None:
        async with self._lock:
            current = self._require_lease(lease)
            task = current.task
            task.status = TaskStatus.PENDING
            task.retry_at = None
            self._leases.pop(task.id, None)
            self._pending.appendleft(task.id)

    async def recover_stale(self, now: datetime) -> int:
        async with self._lock:
            stale = [lease for lease in self._leases.values() if lease.expires_at <= now]
            recovered = 0
            for lease in stale:
                current = self._leases.get(lease.task.id)
                if current is None or current.token != lease.token:
                    continue
                self._leases.pop(lease.task.id, None)
                lease.task.status = TaskStatus.PENDING
                self._pending.append(lease.task.id)
                recovered += 1
            self._promote_due_retries(now)
            return recovered

    async def close(self) -> None:
        async with self._lock:
            self._closed = True

    async def get(self, task_id: UUID) -> Task | None:
        """测试和诊断用只读查询。"""
        async with self._lock:
            return self._tasks.get(task_id)

    def _promote_due_retries(self, now: datetime) -> None:
        timestamp = now.timestamp()
        while self._retry_heap and self._retry_heap[0][0] <= timestamp:
            _, _, task_id = heapq.heappop(self._retry_heap)
            task = self._tasks.get(task_id)
            if task is None or task.status != TaskStatus.RETRY_WAIT:
                continue
            task.status = TaskStatus.PENDING
            task.retry_at = None
            self._pending.append(task.id)

    def _require_lease(self, lease: TaskLease, reject_expired: bool = False) -> TaskLease:
        current = self._leases.get(lease.task.id)
        if current is None or current.owner != lease.owner or current.token != lease.token:
            raise LeaseLostError(f"Task lease is no longer valid: {lease.task.id}")
        if reject_expired and current.expires_at <= utcnow():
            raise LeaseLostError(f"Task lease has expired: {lease.task.id}")
        return current

    def _record_terminal(self, task_id: UUID) -> None:
        self._terminal.append(task_id)
        while len(self._terminal) > self.terminal_history_limit:
            expired_id = self._terminal.popleft()
            task = self._tasks.pop(expired_id, None)
            if task and task.idempotency_key:
                self._idempotency_keys.pop(task.idempotency_key, None)

    def _ensure_open(self) -> None:
        if self._closed:
            raise QueueClosedError("Task queue is closed")
