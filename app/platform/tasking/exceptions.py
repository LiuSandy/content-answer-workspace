class WorkerRuntimeError(RuntimeError):
    """Worker 基础设施异常基类。"""


class QueueClosedError(WorkerRuntimeError):
    pass


class DuplicateTaskError(WorkerRuntimeError):
    pass


class LeaseLostError(WorkerRuntimeError):
    pass


class SchedulerNotRunningError(WorkerRuntimeError):
    pass


class TaskExecutionError(Exception):
    """业务 Handler 可以抛出的任务执行异常基类。"""


class RetryableTaskError(TaskExecutionError):
    pass


class NonRetryableTaskError(TaskExecutionError):
    pass


class TaskTimeoutError(RetryableTaskError):
    pass


class HandlerNotFoundError(NonRetryableTaskError):
    pass
