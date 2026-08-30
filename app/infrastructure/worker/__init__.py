"""通用异步任务调度基础设施。

该包只负责任务生命周期、Worker 调度和失败恢复，不包含任何业务逻辑。
具体业务应通过 TaskHandler 注册到 TaskScheduler。
"""

from .exceptions import (
    DuplicateTaskError,
    HandlerNotFoundError,
    LeaseLostError,
    NonRetryableTaskError,
    QueueClosedError,
    RetryableTaskError,
    SchedulerNotRunningError,
    TaskTimeoutError,
)
from .in_memory_queue import InMemoryTaskQueue
from .models import SchedulerState, Task, TaskLease, TaskStatus
from .notifier import EventTaskNotifier
from .ports import TaskHandler, TaskNotifier, TaskQueue
from .registry import TaskHandlerRegistry
from .retry import ExponentialBackoffRetryPolicy, RetryDecision, RetryPolicy
from .scheduler import TaskScheduler, TaskSchedulerConfig

__all__ = [
    "DuplicateTaskError",
    "EventTaskNotifier",
    "ExponentialBackoffRetryPolicy",
    "HandlerNotFoundError",
    "InMemoryTaskQueue",
    "LeaseLostError",
    "NonRetryableTaskError",
    "QueueClosedError",
    "RetryableTaskError",
    "RetryDecision",
    "RetryPolicy",
    "SchedulerNotRunningError",
    "SchedulerState",
    "Task",
    "TaskHandler",
    "TaskHandlerRegistry",
    "TaskLease",
    "TaskNotifier",
    "TaskQueue",
    "TaskScheduler",
    "TaskSchedulerConfig",
    "TaskStatus",
    "TaskTimeoutError",
]
