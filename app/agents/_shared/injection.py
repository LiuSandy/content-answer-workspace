"""Deterministic prompt-injection checks shared by the two agent graphs.

The guard intentionally matches only high-confidence attempts to override the
application's instructions or disclose protected configuration. Content-writing
requests often contain role-playing language, so generic phrases such as
``act as`` are not blocked on their own.
"""
from __future__ import annotations

import re


_INPUT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?",
        r"forget\s+(?:all\s+)?(?:your|previous|earlier)\s+(?:instructions?|rules?)",
        r"disregard\s+(?:your\s+)?(?:instructions?|guidelines?|rules?)",
        r"override\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)",
        r"(?:show|reveal|print|dump)\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)",
        r"(?:extract|dump|leak|exfiltrate)\s+(?:the\s+)?(?:data|prompt|system|config|secrets?)",
        r"忽略(?:之前|上面|以上|所有)?(?:的)?(?:指令|规则|设定|提示词?)",
        r"忘记(?:你|之前|刚才)?(?:的)?(?:设定|规则|指令|身份)",
        r"(?:告诉|显示|输出|泄露)(?:我|我一下)?(?:你的)?(?:系统)?(?:提示词|prompt|密钥|配置)",
        r"(?:绕过|跳过|关闭)(?:安全|权限|守卫|guard)(?:检查|限制|规则)?",
    )
)

_SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def detect_input_injection(text: str) -> tuple[bool, str | None]:
    """Return whether *text* contains a high-confidence injection attempt."""

    for index, pattern in enumerate(_INPUT_PATTERNS):
        if pattern.search(text or ""):
            return True, f"prompt_injection_pattern_{index}"
    return False, None


def validate_scope(value: str | None, *, field: str) -> tuple[bool, str | None]:
    """Validate checkpoint-safe workspace/owner identifiers."""

    if value is None:
        return True, None
    if not _SCOPE_PATTERN.fullmatch(str(value)):
        return False, f"invalid_{field}"
    return True, None


__all__ = ["detect_input_injection", "validate_scope"]
