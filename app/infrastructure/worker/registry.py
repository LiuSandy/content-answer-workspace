from __future__ import annotations

from .exceptions import HandlerNotFoundError
from .ports import TaskHandler


class TaskHandlerRegistry:
    """维护 task_type 到业务 Handler 的映射。"""

    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, task_type: str, handler: TaskHandler) -> None:
        normalized = task_type.strip()
        if not normalized:
            raise ValueError("task_type must not be empty")
        if normalized in self._handlers:
            raise ValueError(f"Handler already registered: {normalized}")
        self._handlers[normalized] = handler

    def resolve(self, task_type: str) -> TaskHandler:
        try:
            return self._handlers[task_type]
        except KeyError as exc:
            raise HandlerNotFoundError(
                f"No handler registered for task type: {task_type}"
            ) from exc
