"""Phase 4 长期记忆：Extractor + Retriever + Service 测试。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.memory_service import (
    _parse_extraction_json, extract_memories, retrieve_memories,
    delete_memory, clear_all_memories, MEMORY_RETRIEVAL_TIMEOUT_MS,
)


def test_parse_extraction_json_valid_list():
    raw = '[{"memory_type": "explicit", "content": "喜欢幽默风格", "confidence": 0.9}]'
    items = _parse_extraction_json(raw)
    assert len(items) == 1
    assert items[0]["memory_type"] == "explicit"
    assert items[0]["confidence"] == 0.9


def test_parse_extraction_json_rejects_invalid_type():
    raw = '[{"memory_type": "FOO", "content": "x", "confidence": 0.8}]'
    items = _parse_extraction_json(raw)
    # 非法类型回退到 explicit
    assert items[0]["memory_type"] == "explicit"


def test_parse_extraction_json_skips_empty_content():
    raw = '[{"memory_type": "explicit", "content": "", "confidence": 0.5}]'
    items = _parse_extraction_json(raw)
    assert items == []


def test_parse_extraction_json_no_json_raises():
    from app.errors import LLMOutputError
    with pytest.raises(LLMOutputError):
        _parse_extraction_json("纯文本没有 JSON")


@pytest.mark.asyncio
async def test_extract_memories_persists(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.analyze = AsyncMock(
        return_value='[{"memory_type": "explicit", "content": "目标读者是大学生", "confidence": 0.85}]'
    )
    monkeypatch.setattr("app.application.memory_service._get_memory_llm", lambda: fake_llm)

    fake_provider = MagicMock()
    fake_provider.embed = AsyncMock(return_value=[[0.1] * 8])
    monkeypatch.setattr(
        "app.application.memory_service._get_embedding_provider",
        lambda: fake_provider,
    )

    # mock prompt registry render（conftest 已加载 prompts，这里只 patch render）
    from app.prompts.registry import prompt_registry
    rendered_mock = MagicMock()
    rendered_mock.to_llm_request.return_value = MagicMock(
        messages=[MagicMock(content="sys"), MagicMock(content="user")]
    )
    monkeypatch.setattr(prompt_registry, "render", lambda *_a, **_kw: rendered_mock)

    # mock DB session
    added: list = []
    fake_session = MagicMock()
    fake_session.add = MagicMock(side_effect=lambda m: added.append(m))
    fake_session.commit = AsyncMock()
    fake_factory = MagicMock()
    fake_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: fake_factory
    )

    saved = await extract_memories(
        messages=[{"role": "user", "content": "我喜欢幽默风格"}],
        session_id="sess-1",
        workspace_id="default",
    )
    assert len(saved) == 1
    assert saved[0].content == "目标读者是大学生"
    assert saved[0].memory_type == "explicit"


@pytest.mark.asyncio
async def test_retrieve_memories_returns_under_timeout(monkeypatch):
    """spec 3.6：单次记忆检索 ≤ 200ms。"""
    snippet_m = MagicMock()
    snippet_m.id = "00000000-0000-0000-0000-000000000001"
    snippet_m.memory_type = "explicit"
    snippet_m.content = "目标读者是大学生"
    snippet_m.confidence = 0.85
    snippet_m.activation_count = 0
    snippet_m.last_activated_at = None

    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [snippet_m]

    fake_session = MagicMock()
    fake_session.execute = AsyncMock(return_value=fake_result)
    fake_session.commit = AsyncMock()

    fake_factory = MagicMock()
    fake_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: fake_factory
    )

    import time
    start = time.monotonic()
    snippets = await retrieve_memories("目标读者", "default", top_k=5)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 200 + 50  # 给点容差
    assert len(snippets) == 1
    assert snippets[0].content == "目标读者是大学生"


@pytest.mark.asyncio
async def test_retrieve_memories_timeout_returns_empty(monkeypatch):
    """超时时返回空列表，不抛异常。"""
    import asyncio

    async def _slow_factory():
        await asyncio.sleep(0.3)
        return MagicMock()

    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", _slow_factory
    )

    snippets = await retrieve_memories("test", "default")
    assert snippets == []


@pytest.mark.asyncio
async def test_delete_memory_not_found(monkeypatch):
    fake_session = MagicMock()
    fake_session.get = AsyncMock(return_value=None)
    fake_factory = MagicMock()
    fake_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.persistence.session.get_session_factory", lambda: fake_factory
    )

    ok = await delete_memory("00000000-0000-0000-0000-000000000001", "default")
    assert ok is False