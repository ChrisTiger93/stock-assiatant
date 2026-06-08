"""
ChromaDB 向量存储封装
"""
import uuid
from typing import List, Optional
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from config import settings
from memory.embedder import embedder


class VectorStore:
    """ChromaDB 向量存储管理器"""

    COLLECTIONS = {
        "memories": "长期知识记忆",
        "conversation_chunks": "对话片段",
        "knowledge_snippets": "搜索知识片段",
    }

    def __init__(self):
        # 确保持久化目录存在
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._ensure_collections()

    def _ensure_collections(self):
        """确保所有 collection 存在，维度与嵌入模型匹配"""
        dim = embedder.dimension
        for name in self.COLLECTIONS:
            try:
                self._client.get_collection(name)
                logger.info(f"Collection '{name}' already exists")
            except Exception:
                self._client.create_collection(
                    name=name,
                    metadata={
                        "description": self.COLLECTIONS[name],
                        "hnsw:space": "cosine",
                    },
                )
                logger.info(f"Collection '{name}' created (dim={dim})")

    def _get_collection(self, name: str):
        return self._client.get_collection(name)

    async def add(
        self,
        collection: str,
        documents: List[str],
        metadatas: Optional[List[dict]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        添加文档到指定 collection（自动嵌入）

        Returns:
            添加的文档 ID 列表
        """
        if not documents:
            return []

        # 生成 ID
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in documents]

        # 调用嵌入服务
        embeddings = await embedder.embed(documents)

        col = self._get_collection(collection)
        col.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

        logger.debug(f"Added {len(documents)} docs to '{collection}'")
        return ids

    async def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> dict:
        """
        语义检索 —— 返回最相似的文档

        Returns:
            {
                "ids": [[...]],
                "documents": [[...]],
                "metadatas": [[...]],
                "distances": [[...]],
            }
        """
        query_embedding = await embedder.embed_single(query_text)

        col = self._get_collection(collection)
        results = col.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return results

    async def query_multi(
        self,
        query_text: str,
        n_results_per_collection: int = 5,
    ) -> dict[str, dict]:
        """
        跨所有 collection 检索

        Returns:
            {collection_name: query_result_dict}
        """
        results = {}
        for name in self.COLLECTIONS:
            results[name] = await self.query(
                collection=name,
                query_text=query_text,
                n_results=n_results_per_collection,
            )
        return results

    def delete(self, collection: str, ids: List[str]):
        """删除指定文档"""
        col = self._get_collection(collection)
        col.delete(ids=ids)

    def count(self, collection: str) -> int:
        """返回 collection 中的文档数量"""
        col = self._get_collection(collection)
        return col.count()


# 全局单例
vector_store = VectorStore()
