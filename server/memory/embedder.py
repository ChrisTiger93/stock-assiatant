"""
嵌入服务 —— 阿里云 DashScope text-embedding-v2
"""
from typing import List
from dashscope import TextEmbedding
from loguru import logger

from config import settings


class Embedder:
    """文本向量化服务"""

    def __init__(self):
        self.model = settings.embedding_model
        self.api_key = settings.dashscope_api_key
        self._dimension: int | None = None

    @property
    def dimension(self) -> int:
        """延迟获取维度（首次调用后确定）"""
        if self._dimension is None:
            # text-embedding-v2 返回 1536 维
            self._dimension = 1536
        return self._dimension

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """
        将文本列表转换为向量列表

        Args:
            texts: 要嵌入的文本列表

        Returns:
            相同顺序的向量列表，每个向量是 float 列表
        """
        if not texts:
            return []

        all_embeddings = []
        # DashScope 单次最多 25 条
        batch_size = 25
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = TextEmbedding.call(
                model=self.model,
                input=batch,
                api_key=self.api_key,
            )
            if resp.status_code == 200:
                embeddings = [emb["embedding"] for emb in resp.output["embeddings"]]
                all_embeddings.extend(embeddings)
            else:
                logger.error(f"Embedding failed: code={resp.status_code} msg={resp.message}")
                raise RuntimeError(f"Embedding API error: {resp.message}")

        return all_embeddings

    async def embed_single(self, text: str) -> List[float]:
        """嵌入单条文本"""
        results = await self.embed([text])
        return results[0]


# 全局单例
embedder = Embedder()
