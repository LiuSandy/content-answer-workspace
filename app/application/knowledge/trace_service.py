from typing import Any


class TraceService:
    SENSITIVE_KEYS = {"api_key", "authorization", "token", "password", "secret", "cookie"}

    def sanitize_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        cleaned = {}
        for key, value in filters.items():
            if key.lower() in self.SENSITIVE_KEYS:
                cleaned[key] = "[REDACTED]"
            elif isinstance(value, dict):
                cleaned[key] = self.sanitize_filters(value)
            else:
                cleaned[key] = value
        return cleaned
