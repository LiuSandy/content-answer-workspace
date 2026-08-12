from __future__ import annotations

import asyncio
import math

import httpx

from app.core.config import get_knowledge_settings


class RerankerNotConfiguredError(RuntimeError):
    pass


class MockRerankerProvider:
    """Deterministic test-only provider."""

    def __init__(self, model_name: str = "mock-reranker"):
        self.model_name = model_name

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [max(0.1, 0.95 - index * 0.1) for index, _ in enumerate(documents)]


class CrossEncoderRerankerProvider:
    """Batch client for the common `/rerank` cross-encoder API contract."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 8.0,
        max_documents: int = 32,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model
        self.max_documents = max_documents
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        if len(documents) > self.max_documents:
            raise ValueError(f"reranker accepts at most {self.max_documents} documents")
        response: httpx.Response | None = None
        for attempt in range(3):
            response = await self.client.post(
                "/rerank",
                json={"model": self.model_name, "query": query, "documents": documents},
            )
            if response.status_code != 429 and response.status_code < 500:
                break
            if attempt < 2:
                await asyncio.sleep(0.25 * (2**attempt))
        assert response is not None
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list) or len(results) != len(documents):
            raise ValueError("reranker result count does not match documents")
        scores: list[float | None] = [None] * len(documents)
        for item in results:
            if not isinstance(item, dict):
                raise ValueError("reranker result must be an object")
            index = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(documents):
                raise ValueError("reranker returned an invalid index")
            if scores[index] is not None:
                raise ValueError("reranker returned a duplicate index")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("reranker score must be finite and within [0, 1]")
            scores[index] = float(score)
        if any(score is None for score in scores):
            raise ValueError("reranker omitted a document index")
        return [score for score in scores if score is not None]

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


def get_reranker_provider() -> CrossEncoderRerankerProvider:
    settings = get_knowledge_settings()
    if not settings.reranker_api_key or not settings.reranker_base_url:
        raise RerankerNotConfiguredError(
            "Reranker 未配置：请设置独立的 RERANKER_API_KEY 和 RERANKER_BASE_URL"
        )
    return CrossEncoderRerankerProvider(
        api_key=settings.reranker_api_key,
        base_url=settings.reranker_base_url,
        model=settings.reranker_model,
        timeout_seconds=settings.reranker_timeout_seconds,
        max_documents=settings.reranker_max_documents,
    )
