"""兼容旧导入路径；新代码请从 worker.queues 导入。"""

from .queues.in_memory import InMemoryTaskQueue

__all__ = ["InMemoryTaskQueue"]
