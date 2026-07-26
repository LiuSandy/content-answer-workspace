import asyncio
import logging
import random
from openai import AsyncOpenAI
from app.core.config import get_knowledge_settings

logger = logging.getLogger(__name__)


class EmbeddingNotConfiguredError(RuntimeError):
    """未配置 embedding API key 时抛出。

    单独定义此异常是为了让上层（索引/检索）可以区分"配置缺失"与"运行时调用失败"：
    配置缺失必须显式失败并提示用户补配置，绝不允许静默降级为 Mock 向量写入数据库。
    """


class MockEmbeddingProvider:
    """确定性伪向量生成器，仅限测试代码直接实例化。

    生产工厂 get_embedding_provider 永远不会返回此类——伪向量无语义，
    一旦写入 pgvector 会永久污染检索结果且难以察觉。
    """

    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            seed = sum(ord(c) for c in text)
            rng = random.Random(seed)
            vec = [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
            norm = sum(x * x for x in vec) ** 0.5
            norm_vec = [x / norm for x in vec] if norm > 0 else vec
            results.append(norm_vec)
        return results


class OpenAIEmbeddingProvider:
    """OpenAI 兼容 embedding 客户端；按批次调用并做维度校验与归一化。

    批大小从配置读取（EMBEDDING_BATCH_SIZE，默认 20）：
    各服务商上限不同（阿里云百炼 20、OpenAI 2048），取保守默认值。
    """

    def __init__(self):
        settings = get_knowledge_settings()
        self.client = AsyncOpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url
        )
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.batch_size = settings.embedding_batch_size

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        """单批次 embedding，带独立重试。

        重试粒度放在批次级别而非整个请求列表：大文档失败重试时
        已成功的批次不会被重复计费和重复执行。
        """
        retries = [1, 2, 4]
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = await asyncio.wait_for(
                    self.client.embeddings.create(
                        input=batch,
                        model=self.model,
                        dimensions=self.dimensions
                    ),
                    timeout=30.0
                )
                results = []
                for data in response.data:
                    vec = data.embedding
                    if len(vec) != self.dimensions:
                        raise ValueError(f"Expected {self.dimensions} dimensions, got {len(vec)}")
                    norm = sum(x * x for x in vec) ** 0.5
                    norm_vec = [x / norm for x in vec] if norm > 0 else vec
                    results.append(norm_vec)
                if len(results) != len(batch):
                    raise ValueError(f"Expected {len(batch)} embeddings, got {len(results)}")
                return results
            except Exception as e:
                last_error = e
                if attempt < 3:
                    await asyncio.sleep(retries[attempt])
        raise last_error  # type: ignore[misc]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            results.extend(await self._embed_batch(batch))
        return results


def get_embedding_provider():
    """生产 embedding provider 工厂。

    未配置 key 时显式抛 EmbeddingNotConfiguredError 而非返回 Mock：
    静默降级会把无语义的伪向量写入索引，属于必须禁止的占位方案。
    """
    settings = get_knowledge_settings()
    if not settings.embedding_api_key:
        raise EmbeddingNotConfiguredError(
            "Embedding 未配置：请设置 EMBEDDING_API_KEY 或 OPENAI_API_KEY 后重试"
        )
    return OpenAIEmbeddingProvider()
