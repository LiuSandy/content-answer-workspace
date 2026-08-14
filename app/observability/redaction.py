from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = re.compile(
    r"^(authorization|proxy-authorization|cookie|set-cookie|api[_-]?key|apikey|"
    r"access[_-]?token|refresh[_-]?token|password|secret|signature|credential)$",
    re.IGNORECASE,
)
_PATTERNS = (
    re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{8,})"),
    re.compile(r"(?i)([?&](?:token|api[_-]?key|key|signature|password|secret)=)[^&\s]+"),
    re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:)[^@\s/]+(@)"),
    re.compile(r"(?i)(\b(?:authorization|cookie|set-cookie)\s*[:=]\s*)[^,;\s]+"),
)


def redact_text(value: object) -> str:
    text = str(value)
    for pattern in _PATTERNS:
        if pattern.groups == 2:
            text = pattern.sub(rf"\1{REDACTED}\2", text)
        elif pattern.groups == 1 and "sk-" in pattern.pattern:
            text = pattern.sub(REDACTED, text)
        else:
            text = pattern.sub(lambda match: f"{match.group(1)} {REDACTED}" if match.lastindex else REDACTED, text)
    return text


def redact_value(value: Any, key: str | None = None) -> Any:
    if key and _SENSITIVE_KEYS.match(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(k): redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
