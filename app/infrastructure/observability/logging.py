from __future__ import annotations

import logging
import logging.handlers
import os
import queue
import re
import shutil
import sys
import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import RLock

from app.config.runtime import ROOT_DIR

from .context import CONTEXT_FIELDS, get_log_context
from .formatter import ConsoleFormatter, JsonFormatter
from .redaction import redact_text, redact_value


@dataclass(frozen=True)
class LoggingSettings:
    level: str
    directory: Path
    retention_days: int
    max_bytes: int
    backup_count: int
    warnings: tuple[str, ...] = ()


def _positive_int(name: str, default: int, warnings: list[str]) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        if value <= 0:
            raise ValueError
        return value
    except ValueError:
        warnings.append(f"Invalid {name}; using {default}")
        return default


def get_logging_settings() -> LoggingSettings:
    warnings: list[str] = []
    raw_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = raw_level if raw_level in {"INFO", "DEBUG"} else "INFO"
    if raw_level not in {"INFO", "DEBUG"}:
        warnings.append(f"Invalid LOG_LEVEL={raw_level!r}; using INFO")
    raw_dir = Path(os.getenv("LOG_DIR", "logs").strip() or "logs")
    directory = raw_dir if raw_dir.is_absolute() else ROOT_DIR / raw_dir
    directory = directory.resolve()
    return LoggingSettings(
        level=level,
        directory=directory,
        retention_days=_positive_int("LOG_RETENTION_DAYS", 14, warnings),
        max_bytes=_positive_int("LOG_MAX_BYTES", 100 * 1024 * 1024, warnings),
        backup_count=_positive_int("LOG_BACKUP_COUNT", 10, warnings),
        warnings=tuple(warnings),
    )


class ContextRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_log_context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        record.msg = redact_value(record.msg)
        if isinstance(record.args, dict):
            record.args = redact_value(record.args)
        elif record.args:
            record.args = tuple(redact_value(value) for value in record.args)
        for key, value in list(record.__dict__.items()):
            if key not in {"msg", "args", "exc_info"}:
                record.__dict__[key] = redact_value(value, key)
        return True


class ExactLevelFilter(logging.Filter):
    def __init__(self, level: int):
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self.level


class InProcessQueueHandler(logging.handlers.QueueHandler):
    """队列只在本进程线程间传递，保留 exc_info 供 JSON formatter 结构化。"""

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return copy.copy(record)


class DatedLevelFileHandler(logging.Handler):
    _DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def __init__(self, root: Path, level_name: str, max_bytes: int, backup_count: int, retention_days: int):
        super().__init__()
        self.root = root
        self.level_name = level_name.lower()
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.retention_days = retention_days
        self._date: date | None = None
        self._stream = None
        self._lock = RLock()

    def _path(self, day: date) -> Path:
        return self.root / day.isoformat() / f"{self.level_name}.log"

    def _open_for(self, day: date) -> None:
        if self._stream:
            self._stream.close()
        path = self._path(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        self._stream = path.open("a", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        self._date = day
        self._cleanup(day)

    def _rotate_if_needed(self, message: str) -> None:
        assert self._date is not None
        path = self._path(self._date)
        if not path.exists() or path.stat().st_size + len(message.encode("utf-8")) + 1 <= self.max_bytes:
            return
        if self._stream:
            self._stream.close()
            self._stream = None
        oldest = path.with_name(f"{path.name}.{self.backup_count}")
        oldest.unlink(missing_ok=True)
        for index in range(self.backup_count - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                source.replace(path.with_name(f"{path.name}.{index + 1}"))
        if path.exists():
            path.replace(path.with_name(f"{path.name}.1"))
        self._stream = path.open("a", encoding="utf-8")

    def _cleanup(self, today: date) -> None:
        cutoff = today - timedelta(days=self.retention_days - 1)
        if not self.root.exists():
            return
        for child in self.root.iterdir():
            if not child.is_dir() or not self._DATE_DIR.fullmatch(child.name):
                continue
            try:
                child_date = date.fromisoformat(child.name)
            except ValueError:
                continue
            if child_date < cutoff:
                shutil.rmtree(child)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            day = datetime.fromtimestamp(record.created).astimezone().date()
            with self._lock:
                if self._date != day or self._stream is None:
                    self._open_for(day)
                self._rotate_if_needed(message)
                self._stream.write(message + "\n")
                self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self._lock:
            if self._stream:
                self._stream.close()
                self._stream = None
        super().close()


_listener: logging.handlers.QueueListener | None = None
_queue_handler: logging.handlers.QueueHandler | None = None


def configure_logging(settings: LoggingSettings | None = None) -> LoggingSettings:
    global _listener, _queue_handler
    if _listener is not None:
        return settings or get_logging_settings()
    settings = settings or get_logging_settings()
    settings.directory.mkdir(parents=True, exist_ok=True)
    json_formatter = JsonFormatter()
    handlers: list[logging.Handler] = []
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter(colors=sys.stdout.isatty()))
    handlers.append(console)
    levels = [logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]
    if settings.level == "DEBUG":
        levels.insert(0, logging.DEBUG)
    for level in levels:
        handler = DatedLevelFileHandler(
            settings.directory, logging.getLevelName(level), settings.max_bytes,
            settings.backup_count, settings.retention_days,
        )
        handler.addFilter(ExactLevelFilter(level))
        handler.setFormatter(json_formatter)
        handlers.append(handler)
    log_queue: queue.SimpleQueue = queue.SimpleQueue()
    _queue_handler = InProcessQueueHandler(log_queue)
    _queue_handler.addFilter(ContextRedactionFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, settings.level))
    root.addHandler(_queue_handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(name)
        target.handlers.clear()
        target.propagate = True
    _listener = logging.handlers.QueueListener(log_queue, *handlers, respect_handler_level=True)
    _listener.start()
    logger = logging.getLogger(__name__)
    for warning in settings.warnings:
        logger.warning(warning)
    return settings


def shutdown_logging() -> None:
    global _listener, _queue_handler
    if _listener:
        _listener.stop()
        for handler in _listener.handlers:
            handler.close()
    root = logging.getLogger()
    if _queue_handler in root.handlers:
        root.removeHandler(_queue_handler)
    _listener = None
    _queue_handler = None
