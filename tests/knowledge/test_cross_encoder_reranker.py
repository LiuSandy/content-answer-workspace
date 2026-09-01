import math
from types import SimpleNamespace

import httpx
import pytest

from app.plugins.rerankers import provider as reranker_module
from app.plugins.rerankers.provider import (
    CrossEncoderRerankerProvider,
    DashScopeVLRerankerProvider,
    RerankerNotConfiguredError,
    get_reranker_provider,
)


@pytest.mark.asyncio
async def test_cross_encoder_batches_documents_and_restores_index_order():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [
            {"index": 1, "relevance_score": 0.2},
            {"index": 0, "relevance_score": 0.9},
        ]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://rerank.test")
    provider = CrossEncoderRerankerProvider(
        api_key="secret", base_url="https://rerank.test", model="reranker", client=client
    )
    try:
        assert await provider.rerank("query", ["first", "second"]) == [0.9, 0.2]
        assert len(requests) == 1
        assert b'"documents":["first","second"]' in requests[0].content
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("results", [
    [{"index": 0, "relevance_score": 0.5}],
    [{"index": 0, "relevance_score": 0.5}, {"index": 0, "relevance_score": 0.4}],
    [{"index": 0, "relevance_score": math.nan}, {"index": 1, "relevance_score": 0.4}],
])
async def test_cross_encoder_rejects_malformed_results(results):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": results})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://rerank.test")
    provider = CrossEncoderRerankerProvider(
        api_key="secret", base_url="https://rerank.test", model="reranker", client=client
    )
    try:
        with pytest.raises(ValueError):
            await provider.rerank("query", ["first", "second"])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_dashscope_vl_uses_dedicated_endpoint_and_contract():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"output": {"results": [
            {"index": 1, "relevance_score": 0.2},
            {"index": 0, "relevance_score": 0.9},
        ]}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DashScopeVLRerankerProvider(
        api_key="secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        model="qwen3-vl-rerank",
        client=client,
    )
    try:
        assert await provider.rerank("query", ["first", "second"]) == [0.9, 0.2]
        assert len(requests) == 1
        assert str(requests[0].url) == (
            "https://workspace.cn-beijing.maas.aliyuncs.com/"
            "api/v1/services/rerank/text-rerank/text-rerank"
        )
        assert requests[0].headers["Authorization"] == "Bearer secret"
        assert requests[0].read().decode() == (
            '{"model":"qwen3-vl-rerank","input":{"query":{"text":"query"},'
            '"documents":[{"text":"first"},{"text":"second"}]},'
            '"parameters":{"return_documents":false,"top_n":2}}'
        )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_dashscope_vl_rejects_missing_output_results():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [
            {"index": 0, "relevance_score": 0.9},
        ]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DashScopeVLRerankerProvider(
        api_key="secret",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com",
        model="qwen3-vl-rerank",
        client=client,
    )
    try:
        with pytest.raises(ValueError, match="output.results"):
            await provider.rerank("query", ["first"])
    finally:
        await client.aclose()


def test_factory_selects_dashscope_vl_provider(monkeypatch):
    monkeypatch.setattr(
        reranker_module,
        "get_knowledge_settings",
        lambda: SimpleNamespace(
            reranker_api_key="secret",
            reranker_base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            reranker_model="qwen3-vl-rerank",
            reranker_timeout_seconds=8.0,
            reranker_max_documents=32,
        ),
    )

    provider = get_reranker_provider()
    try:
        assert isinstance(provider, DashScopeVLRerankerProvider)
    finally:
        # The factory owns a real AsyncClient; close it without requiring an event loop fixture.
        import asyncio

        asyncio.run(provider.aclose())


def test_factory_rejects_missing_model(monkeypatch):
    monkeypatch.setattr(
        reranker_module,
        "get_knowledge_settings",
        lambda: SimpleNamespace(
            reranker_api_key="secret",
            reranker_base_url="https://rerank.test",
            reranker_model="",
            reranker_timeout_seconds=8.0,
            reranker_max_documents=32,
        ),
    )

    with pytest.raises(RerankerNotConfiguredError, match="RERANKER_MODEL"):
        get_reranker_provider()
