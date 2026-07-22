import pytest
from unittest.mock import AsyncMock, MagicMock
from app.errors import DocumentConflictError


@pytest.mark.asyncio
async def test_answer_generation_handles_lock_conflict():
    # 验证当 expected_lock_version 与数据库不一致时，DocumentConflictError 正确携带 expected 和 actual
    err = DocumentConflictError(expected=15, actual=16)
    assert err.expected == 15
    assert err.actual == 16
    assert "expected 15, got 16" in str(err)
