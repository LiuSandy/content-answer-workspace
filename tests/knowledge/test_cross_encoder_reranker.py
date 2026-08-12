import math

import httpx
import pytest

from app.infrastructure.knowledge.reranker import CrossEncoderRerankerProvider


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
