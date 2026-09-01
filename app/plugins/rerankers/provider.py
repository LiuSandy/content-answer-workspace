from __future__ import annotations

import asyncio
import math
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.platform.config.runtime import get_knowledge_settings
from app.modules.knowledge.ports import RerankerNotConfiguredError


class MockRerankerProvider:
    """Deterministic test-only provider."""

    def __init__(self, model_name: str = "mock-reranker"):
        self.model_name = model_name

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [max(0.1, 0.95 - index * 0.1) for index, _ in enumerate(documents)]


def _parse_scores(results: object, document_count: int, *, field_name: str) -> list[float]:
    if not isinstance(results, list) or len(results) != document_count:
        raise ValueError(f"reranker {field_name} count does not match documents")
    scores: list[float | None] = [None] * document_count
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("reranker result must be an object")
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < document_count:
            raise ValueError("reranker returned an invalid index")
        if scores[index] is not None:
            raise ValueError("reranker returned a duplicate index")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("reranker score must be finite and within [0, 1]")
        scores[index] = float(score)
    if any(score is None for score in scores):
        raise ValueError("reranker omitted a document index")
    return [score for score in scores if score is not None]


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
        return _parse_scores(payload.get("results"), len(documents), field_name="results")

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


class DashScopeVLRerankerProvider:
    """Alibaba Cloud DashScope adapter for ``qwen3-vl-rerank``.

    The multimodal model does not implement the common OpenAI-compatible
    rerank contract: it uses a dedicated service endpoint, nests inputs under
    ``input`` and returns scores under ``output.results``.  The retrieval
    pipeline currently supplies text only, represented explicitly as text
    modalities so this adapter can later accept image/video candidates without
    changing the wire protocol.
    """

    _SERVICE_PATH = "/api/v1/services/rerank/text-rerank/text-rerank"

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
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("RERANKER_BASE_URL must be an absolute HTTP(S) URL")
        configured_path = parsed.path.rstrip("/")
        if configured_path.endswith(self._SERVICE_PATH):
            self.endpoint = base_url.rstrip("/")
        else:
            self.endpoint = urlunsplit(
                (parsed.scheme, parsed.netloc, self._SERVICE_PATH, "", "")
            )
        self.model_name = model
        self.max_documents = max_documents
        self._api_key = api_key
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        if len(documents) > self.max_documents:
            raise ValueError(f"reranker accepts at most {self.max_documents} documents")

        response: httpx.Response | None = None
        for attempt in range(3):
            response = await self.client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model_name,
                    "input": {
                        "query": {"text": query},
                        "documents": [{"text": document} for document in documents],
                    },
                    "parameters": {
                        "return_documents": False,
                        "top_n": len(documents),
                    },
                },
            )
            if response.status_code != 429 and response.status_code < 500:
                break
            if attempt < 2:
                await asyncio.sleep(0.25 * (2**attempt))

        assert response is not None
        response.raise_for_status()
        payload = response.json()
        output = payload.get("output")
        results = output.get("results") if isinstance(output, dict) else None
        return _parse_scores(
            results,
            len(documents),
            field_name="output.results",
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


def get_reranker_provider() -> CrossEncoderRerankerProvider | DashScopeVLRerankerProvider:
    settings = get_knowledge_settings()
    missing: list[str] = []
    if not settings.reranker_api_key:
        missing.append("RERANKER_API_KEY")
    if not settings.reranker_base_url:
        missing.append("RERANKER_BASE_URL")
    if not settings.reranker_model:
        missing.append("RERANKER_MODEL")
    if missing:
        raise RerankerNotConfiguredError(
            f"Reranker 未配置：请设置 {', '.join(missing)}"
        )
    provider_class = (
        DashScopeVLRerankerProvider
        if settings.reranker_model == "qwen3-vl-rerank"
        else CrossEncoderRerankerProvider
    )
    return provider_class(
        api_key=settings.reranker_api_key,
        base_url=settings.reranker_base_url,
        model=settings.reranker_model,
        timeout_seconds=settings.reranker_timeout_seconds,
        max_documents=settings.reranker_max_documents,
    )
