class MockRerankerProvider:
    def __init__(self, model_name: str = "mock-reranker"):
        self.model_name = model_name

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        # 为调试提供归一化重排得分
        scores = []
        for idx, doc in enumerate(documents):
            score = max(0.1, 0.95 - (idx * 0.1))
            scores.append(score)
        return scores
