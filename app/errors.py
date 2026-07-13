"""统一错误类型；对应架构文档第 14 节的错误分类。

所有业务异常继承自 AppError，携带稳定的 error_code 供前端消费。
后端不向前端暴露堆栈信息。
"""
from __future__ import annotations


class AppError(Exception):
    """所有业务异常的基类。"""
    error_code: str = "internal_error"


class ValidationError(AppError):
    error_code = "validation_error"


class UnsupportedSourceError(AppError):
    error_code = "unsupported_source"

    def __init__(self, url_or_platform: str) -> None:
        super().__init__(f"Unsupported source: {url_or_platform}")
        self.url_or_platform = url_or_platform


class SourceAuthError(AppError):
    error_code = "source_auth_error"


class SourceRateLimitError(AppError):
    error_code = "source_rate_limit"


class SourceUnavailableError(AppError):
    error_code = "source_unavailable"


class LLMRateLimitError(AppError):
    error_code = "llm_rate_limit"


class LLMOutputError(AppError):
    error_code = "llm_output_error"


class DocumentConflictError(AppError):
    """409 乐观锁冲突；客户端需要重新获取最新 lock_version 后重试。"""
    error_code = "document_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"Lock version conflict: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


class OperationTimeoutError(AppError):
    error_code = "operation_timeout"
