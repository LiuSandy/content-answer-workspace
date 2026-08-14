from unittest.mock import MagicMock
from app.application.knowledge.trace_service import TraceService


def test_trace_service_sanitization():
    # TraceService requires an AsyncSession; use a mock for unit-testing sanitize_filters
    mock_session = MagicMock()
    service = TraceService(session=mock_session)
    filters = {"api_key": "secret_key_123", "workspace_id": "default"}
    cleaned = service.sanitize_filters(filters)
    assert "api_key" not in cleaned or cleaned["api_key"] == "[REDACTED]"
    assert cleaned["workspace_id"] == "default"
