from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from .exceptions import NonRetryableTaskError, RetryableTaskError
from .models import Task


@dataclass(frozen=True, slots=True)
class RetryDecision:
    should_retry: bool
    delay: timedelta | None
    reason: str


class RetryPolicy(Protocol):
    def decide(self, task: Task, error: BaseException) -> RetryDecision: ...


class ExponentialBackoffRetryPolicy:
    """按任务尝试次数进行指数退避。"""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 300.0,
        retry_unknown_errors: bool = True,
    ) -> None:
        if base_delay < 0 or max_delay < base_delay:
            raise ValueError("retry delay bounds are invalid")
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retry_unknown_errors = retry_unknown_errors

    def decide(self, task: Task, error: BaseException) -> RetryDecision:
        if isinstance(error, NonRetryableTaskError):
            return RetryDecision(False, None, "non_retryable_error")
        if task.attempt >= task.max_attempts:
            return RetryDecision(False, None, "max_attempts_reached")
        if not self.retry_unknown_errors and not isinstance(error, RetryableTaskError):
            return RetryDecision(False, None, "unknown_error")
        seconds = min(
            self.max_delay,
            self.base_delay * (2 ** max(task.attempt - 1, 0)),
        )
        return RetryDecision(True, timedelta(seconds=seconds), "retryable_error")
