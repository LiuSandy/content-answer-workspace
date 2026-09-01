from __future__ import annotations

import json
import logging
import asyncio
from datetime import datetime

from app.platform.observability.context import bind_log_context, get_log_context
from app.platform.observability.formatter import ConsoleFormatter, JsonFormatter
from app.platform.observability.logging import (
    DatedLevelFileHandler,
    ExactLevelFilter,
    LoggingSettings,
    configure_logging,
    get_logging_settings,
    shutdown_logging,
)
from app.platform.observability.redaction import REDACTED, redact_value


def test_logging_settings_default_and_debug(monkeypatch, tmp_path):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    assert get_logging_settings().level == "INFO"
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert get_logging_settings().level == "DEBUG"
    monkeypatch.setenv("LOG_LEVEL", "TRACE")
    settings = get_logging_settings()
    assert settings.level == "INFO"
    assert settings.warnings


def test_json_formatter_includes_context_and_exception():
    formatter = JsonFormatter()
    with bind_log_context(request_id="req-1", job_id="job-1"):
        try:
            raise RuntimeError("bad Bearer secret-token")
        except RuntimeError:
            record = logging.getLogger("test").makeRecord(
                "test", logging.ERROR, __file__, 10, "failed", (), exc_info=__import__("sys").exc_info()
            )
            from app.platform.observability.logging import ContextRedactionFilter
            ContextRedactionFilter().filter(record)
            data = json.loads(formatter.format(record))
    assert data["request_id"] == "req-1"
    assert data["job_id"] == "job-1"
    assert REDACTED in data["exception"]["message"]
    assert "secret-token" not in data["exception"]["stacktrace"]


def test_console_formatter_is_compact_and_omits_null_context():
    formatter = ConsoleFormatter(colors=False)
    record = logging.makeLogRecord({
        "name": "app.modules.conversation.api.router",
        "levelno": logging.INFO,
        "levelname": "INFO",
        "msg": "Chat started",
        "request_id": "req-1",
        "run_id": "run-1",
        "job_id": None,
        "method": "POST",
    })

    rendered = formatter.format(record)

    assert "INFO" in rendered
    assert "app.modules.conversation.api.router" in rendered
    assert "Chat started" in rendered
    assert "request_id=req-1" in rendered
    assert "run_id=run-1" in rendered
    assert "method=POST" in rendered
    assert "job_id" not in rendered
    assert not rendered.startswith("{")


def test_console_formatter_renders_readable_redacted_exception():
    formatter = ConsoleFormatter(colors=False)
    try:
        raise RuntimeError("Bearer console-secret")
    except RuntimeError:
        record = logging.getLogger("test.console").makeRecord(
            "test.console", logging.ERROR, __file__, 10, "failed", (),
            exc_info=__import__("sys").exc_info(),
        )
    from app.platform.observability.logging import ContextRedactionFilter
    ContextRedactionFilter().filter(record)

    rendered = formatter.format(record)

    assert "Traceback (most recent call last)" in rendered
    assert REDACTED in rendered
    assert "console-secret" not in rendered


def test_redacts_nested_sensitive_values():
    value = redact_value({"api_key": "secret", "nested": {"password": "p"}, "safe": "ok"})
    assert value == {"api_key": REDACTED, "nested": {"password": REDACTED}, "safe": "ok"}


def test_exact_level_file_routing_and_size_rotation(tmp_path):
    formatter = JsonFormatter()
    info = DatedLevelFileHandler(tmp_path, "INFO", max_bytes=200, backup_count=2, retention_days=14)
    info.addFilter(ExactLevelFilter(logging.INFO))
    info.setFormatter(formatter)
    warning = DatedLevelFileHandler(tmp_path, "WARNING", max_bytes=10_000, backup_count=2, retention_days=14)
    warning.addFilter(ExactLevelFilter(logging.WARNING))
    warning.setFormatter(formatter)
    for _ in range(3):
        record = logging.makeLogRecord({"name": "test", "levelno": logging.INFO, "levelname": "INFO", "msg": "x" * 80})
        if info.filter(record):
            info.emit(record)
        assert not warning.filter(record)
    info.close()
    warning.close()
    day = datetime.now().astimezone().date().isoformat()
    assert (tmp_path / day / "info.log").exists()
    assert (tmp_path / day / "info.log.1").exists()
    assert not (tmp_path / day / "warning.log").exists()


def test_configure_logging_writes_exact_level_files(tmp_path):
    settings = LoggingSettings("DEBUG", tmp_path, 14, 1_000_000, 2)
    configure_logging(settings)
    logger = logging.getLogger("test.routing")
    logger.debug("debug message")
    logger.info("info message")
    logger.error("error message")
    shutdown_logging()
    day = datetime.now().astimezone().date().isoformat()
    assert "debug message" in (tmp_path / day / "debug.log").read_text()
    assert "info message" in (tmp_path / day / "info.log").read_text()
    assert "error message" in (tmp_path / day / "error.log").read_text()
    assert "error message" not in (tmp_path / day / "info.log").read_text()


def test_async_log_contexts_are_isolated():
    async def worker(job_id: str):
        with bind_log_context(job_id=job_id):
            await asyncio.sleep(0)
            return get_log_context()["job_id"]

    async def run():
        return await asyncio.gather(worker("job-a"), worker("job-b"))

    assert asyncio.run(run()) == ["job-a", "job-b"]
    assert "job_id" not in get_log_context()
