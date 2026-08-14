from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from .context import CONTEXT_FIELDS
from .redaction import redact_text, redact_value

_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_CONSOLE_IGNORED_EXTRAS = {"color_message"}


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: redact_value(value, key)
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_FIELDS
        and key not in CONTEXT_FIELDS
        and key not in _CONSOLE_IGNORED_EXTRAS
        and not key.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = redact_text(record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        for field in CONTEXT_FIELDS:
            payload[field] = redact_value(getattr(record, field, None), field)
        payload.update({
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        })
        if record.exc_info:
            payload["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": redact_text(record.exc_info[1]),
                "stacktrace": redact_text(self.formatException(record.exc_info)),
            }
        else:
            payload["exception"] = None
        extras = _extra_fields(record)
        if extras:
            payload["fields"] = extras
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """面向终端阅读的紧凑格式；完整结构化字段仍由文件 JSON 保存。"""

    _RESET = "\033[0m"
    _DIM = "\033[2m"
    _LEVEL_COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[1;31m",
    }

    def __init__(self, colors: bool = False):
        super().__init__()
        self.colors = colors

    @staticmethod
    def _render_value(value: Any) -> str:
        if isinstance(value, str):
            rendered = value
        elif isinstance(value, (int, float, bool)) or value is None:
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
        else:
            rendered = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
        rendered = rendered.replace("\n", "\\n")
        return rendered if len(rendered) <= 200 else rendered[:197] + "..."

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).astimezone().strftime("%H:%M:%S")
        level = record.levelname
        display_level = f"{level:<8}"
        if self.colors:
            timestamp = f"{self._DIM}{timestamp}{self._RESET}"
            display_level = f"{self._LEVEL_COLORS.get(level, '')}{display_level}{self._RESET}"
        line = f"{timestamp} {display_level} {record.name:<38} | {redact_text(record.getMessage())}"
        fields: dict[str, Any] = {}
        for key in CONTEXT_FIELDS:
            value = redact_value(getattr(record, key, None), key)
            if value is not None:
                fields[key] = value
        fields.update(_extra_fields(record))
        if fields:
            line += "  " + " ".join(
                f"{key}={self._render_value(value)}" for key, value in fields.items()
            )
        if record.exc_info:
            line += "\n" + redact_text(self.formatException(record.exc_info))
        return line
