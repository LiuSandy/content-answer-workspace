import random


class MockEmbeddingProvider:
    def __init__(self, dimensions: int = 1536):
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            # 种子化伪随机数，使得相同字符串产生确定性的测试向量
            seed = sum(ord(c) for c in text)
            rng = random.Random(seed)
            vec = [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
            # L2 归一化
            norm = sum(x * x for x in vec) ** 0.5
            norm_vec = [x / norm for x in vec] if norm > 0 else vec
            results.append(norm_vec)
        return results
