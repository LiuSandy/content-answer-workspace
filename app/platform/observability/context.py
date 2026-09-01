from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from contextvars import Token
from typing import Iterator

CONTEXT_FIELDS = (
    "request_id", "run_id", "job_id", "task_id", "trace_id", "chat_id",
    "document_id", "source_file_id", "operation_id", "plan_id",
    "page_number", "scheduler_job_id",
)

_log_context: ContextVar[dict[str, object]] = ContextVar("log_context", default={})


def get_log_context() -> dict[str, object]:
    return dict(_log_context.get())


def set_log_context(**values: object) -> Token:
    current = get_log_context()
    current.update({key: value for key, value in values.items() if key in CONTEXT_FIELDS and value is not None})
    return _log_context.set(current)


def reset_log_context(token: Token) -> None:
    _log_context.reset(token)


@contextmanager
def bind_log_context(**values: object) -> Iterator[None]:
    token = set_log_context(**values)
    try:
        yield
    finally:
        reset_log_context(token)
