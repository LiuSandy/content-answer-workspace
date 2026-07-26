import asyncio
import logging
import re
from openai import AsyncOpenAI
from app.core.config import get_knowledge_settings

logger = logging.getLogger(__name__)


class RerankerNotConfiguredError(RuntimeError):
    """未配置 reranker API key 时抛出。

    单独定义此异常是为了让检索层能显式感知"rerank 不可用"并走
    有明确标记的降级路径（RRF 排序 + fallback_reason），
    而不是拿 Mock 伪分数冒充真实相关性。
    """


class MockRerankerProvider:
    """按名次递减的伪打分器，仅限测试代码直接实例化。

    生产工厂 get_reranker_provider 永远不会返回此类——伪分数会让
    证据阈值判定（evidence_threshold）完全失真。
    """

    def __init__(self, model_name: str = "mock-reranker"):
        self.model_name = model_name

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        scores = []
        for idx, doc in enumerate(documents):
            score = max(0.1, 0.95 - (idx * 0.1))
            scores.append(score)
        return scores


# 匹配独立出现的 0~1 小数（含 0/1 整数），前后不能紧跟其他数字，
# 避免 "10 分" 被误解析成 1.0
_SCORE_PATTERN = re.compile(r"(?<![\d.])(?:0(?:\.\d+)?|1(?:\.0+)?)(?![\d.])")


class LLMRerankerProvider:
    """用 LLM 对候选文档逐条打分的 reranker。

    单独封装是为了隔离打分 prompt 与分数解析逻辑，
    上层只依赖 rerank(query, docs) -> scores 接口。
    """

    def __init__(self):
        settings = get_knowledge_settings()
        self.client = AsyncOpenAI(
            api_key=settings.reranker_api_key,
            base_url=settings.reranker_base_url
        )
        self.model = settings.reranker_model

    async def _score_document(self, query: str, doc: str) -> float:
        prompt = (
            "请评估文档片段与查询问题的相关程度，只输出一个 0.0 到 1.0 之间的小数，"
            "不要输出任何其他文字。\n"
            f"问题：{query}\n文档片段：{doc}"
        )
        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0
                ),
                timeout=8.0
            )
            content = response.choices[0].message.content.strip()
            match = _SCORE_PATTERN.search(content)
            if match:
                score = float(match.group(0))
                if 0.0 <= score <= 1.0:
                    return score
            logger.warning("Reranker 输出无法解析为分数: %r", content[:100])
            return 0.5
        except Exception as e:
            logger.warning(f"Reranker error: {e}")
            return 0.5

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []

        semaphore = asyncio.Semaphore(8)

        async def sem_score(doc: str):
            async with semaphore:
                return await self._score_document(query, doc)

        tasks = [sem_score(doc) for doc in documents]
        return await asyncio.gather(*tasks)


def get_reranker_provider():
    """生产 reranker 工厂。

    未配置 key 时显式抛 RerankerNotConfiguredError 而非返回 Mock：
    伪分数会污染证据判定，属于必须禁止的占位方案。
    """
    settings = get_knowledge_settings()
    if not settings.reranker_api_key:
        raise RerankerNotConfiguredError(
            "Reranker 未配置：请设置 RERANKER_API_KEY 或 OPENAI_API_KEY 后重试"
        )
    return LLMRerankerProvider()
