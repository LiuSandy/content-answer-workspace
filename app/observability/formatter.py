from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from .context import CONTEXT_FIELDS
from .redaction import redact_text, redact_value

_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


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
        extras = {
            key: redact_value(value, key)
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_FIELDS and key not in CONTEXT_FIELDS and not key.startswith("_")
        }
        if extras:
            payload["fields"] = extras
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
