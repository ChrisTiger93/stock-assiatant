"""
记忆管理器 —— 编排向量存储、嵌入、提取的完整记忆生命周期
"""
import math
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from config import settings
from memory.store import vector_store
from memory.extractor import extract_from_conversation, generate_conversation_title
from memory.embedder import embedder
from models.db import MemoryRef, Conversation


class MemoryManager:
    """管理三层记忆的生命周期"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ==================== 写入 ====================

    async def add_conversation_chunk(
        self,
        conversation_id: str,
        text: str,
        chunk_index: int,
    ):
        """将对话片段写入短期向量记忆"""
        chroma_id = f"chunk_{conversation_id}_{chunk_index}"
        await vector_store.add(
            collection="conversation_chunks",
            documents=[text],
            metadatas=[{
                "conversation_id": conversation_id,
                "chunk_index": chunk_index,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }],
            ids=[chroma_id],
        )
        # 写入引用表
        ref = MemoryRef(
            id=uuid4(),
            chroma_id=chroma_id,
            collection="conversation_chunks",
            source_type="conversation_summary",
            source_conversation_id=conversation_id,
        )
        self.db.add(ref)
        await self.db.commit()

    async def finalize_conversation(
        self,
        conversation_id: str,
        messages: List[dict],
    ):
        """对话结束后：提取摘要和事实，写入长期记忆"""
        # 提取
        extracted = await extract_from_conversation(messages)

        # 更新对话标题和摘要
        if extracted.get("summary"):
            await self.db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(summary=extracted["summary"])
            )

        if not extracted.get("facts"):
            logger.info(f"No facts extracted from conversation {conversation_id}")
            return

        # 写入长期记忆向量库
        for fact in extracted["facts"]:
            chroma_id = f"mem_{uuid4().hex[:12]}"
            await vector_store.add(
                collection="memories",
                documents=[fact["content"]],
                metadatas=[{
                    "tags": ",".join(fact.get("tags", [])),
                    "importance": fact.get("importance", 0.5),
                    "source_conversation_id": conversation_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }],
                ids=[chroma_id],
            )
            # 写入引用表
            ref = MemoryRef(
                id=uuid4(),
                chroma_id=chroma_id,
                collection="memories",
                title=fact["content"][:100],
                tags=fact.get("tags", []),
                importance=fact.get("importance", 0.5),
                source_type="extracted",
                source_conversation_id=conversation_id,
            )
            self.db.add(ref)

        await self.db.commit()
        logger.info(
            f"Saved {len(extracted['facts'])} facts from conversation {conversation_id}"
        )

    async def add_knowledge_snippet(
        self,
        content: str,
        url: str = "",
        query: str = "",
    ):
        """添加搜索知识片段"""
        chroma_id = f"snippet_{uuid4().hex[:12]}"
        await vector_store.add(
            collection="knowledge_snippets",
            documents=[content],
            metadatas=[{
                "url": url,
                "source": "search",
                "search_query": query,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }],
            ids=[chroma_id],
        )
        ref = MemoryRef(
            id=uuid4(),
            chroma_id=chroma_id,
            collection="knowledge_snippets",
            title=content[:100],
            source_type="search_result",
        )
        self.db.add(ref)
        await self.db.commit()

    # ==================== 检索 ====================

    async def retrieve(self, query: str) -> List[dict]:
        """
        检索与查询相关的记忆（混合三层的语义检索结果）

        Returns:
            排序去重后的记忆列表，每项为 {content, collection, similarity, importance, tags}
        """
        top_k = settings.memory_top_k

        # 跨 collection 检索
        memory_results = await vector_store.query(
            "memories", query, n_results=top_k
        )
        chunk_results = await vector_store.query(
            "conversation_chunks", query, n_results=min(top_k, 3)
        )
        snippet_results = await vector_store.query(
            "knowledge_snippets", query, n_results=min(top_k, 3)
        )

        # 合并结果
        merged = []
        for collection, results in [
            ("memories", memory_results),
            ("conversation_chunks", chunk_results),
            ("knowledge_snippets", snippet_results),
        ]:
            if not results["documents"] or not results["documents"][0]:
                continue

            docs = results["documents"][0]
            metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
            dists = results["distances"][0] if results["distances"] else [0] * len(docs)

            for doc, meta, dist in zip(docs, metas, dists):
                # 余弦距离 → 相似度（0~1）
                similarity = 1.0 - (dist / 2.0) if dist else 1.0

                # 时间衰减
                created_at = meta.get("created_at", "")
                time_weight = self._time_decay(created_at)

                # 重要性
                importance = float(meta.get("importance", 0.5))

                # 综合分数 = 语义相似度 × 重要性 × 时间衰减
                score = similarity * max(importance, 0.1) * time_weight

                merged.append({
                    "content": doc,
                    "collection": collection,
                    "similarity": round(similarity, 4),
                    "importance": importance,
                    "time_weight": round(time_weight, 4),
                    "score": round(score, 4),
                    "tags": meta.get("tags", "").split(",") if meta.get("tags") else [],
                })

        # 按综合分数排序
        merged.sort(key=lambda m: m["score"], reverse=True)

        # 去重（相似内容取最高分）
        seen = set()
        deduped = []
        for m in merged:
            key = m["content"][:50]
            if key not in seen:
                seen.add(key)
                deduped.append(m)

        logger.info(
            f"Retrieved {len(deduped)} unique memories for query: {query[:50]}..."
        )
        return deduped[:top_k * 2]  # 多返回一些让 orchestrator 截断

    async def build_context_for_prompt(self, query: str, max_tokens: int = 1500) -> str:
        """
        检索相关记忆并构建用于注入 Prompt 的上下文字符串
        """
        memories = await self.retrieve(query)
        if not memories:
            return ""

        lines = ["## 相关记忆"]
        char_count = 0
        for i, m in enumerate(memories):
            source = {
                "memories": "长期记忆",
                "conversation_chunks": "近期对话",
                "knowledge_snippets": "知识库",
            }.get(m["collection"], "其他")

            line = f"- [{source}] {m['content']} (相关度:{m['similarity']})"
            # 控制总长度
            if char_count + len(line) > max_tokens * 2:  # 粗略估算 1 token ≈ 2 chars(中文)
                break
            lines.append(line)
            char_count += len(line)

        return "\n".join(lines)

    def _time_decay(self, created_at_str: str) -> float:
        """时间衰减：越新的记忆权重越高，7 天半衰期"""
        if not created_at_str:
            return 0.5
        try:
            created = datetime.fromisoformat(created_at_str)
            now = datetime.now(timezone.utc)
            # 确保 created 有时区信息
            if created.tzinfo is None:
                from datetime import timezone as tz
                created = created.replace(tzinfo=tz.utc)

            days_ago = (now - created).total_seconds() / 86400
            # 半衰期 7 天
            return math.exp(-0.1 * days_ago)
        except Exception:
            return 0.5

    # ==================== 管理 ====================

    async def delete_memory(self, chroma_id: str, collection: str):
        """删除一条记忆"""
        vector_store.delete(collection, [chroma_id])
        await self.db.execute(
            update(MemoryRef)
            .where(MemoryRef.chroma_id == chroma_id)
            .values(importance=0)
        )
        await self.db.commit()

    async def list_memories(self, collection: str = "memories", limit: int = 50) -> List[dict]:
        """列出记忆引用"""
        result = await self.db.execute(
            select(MemoryRef)
            .where(MemoryRef.collection == collection, MemoryRef.importance > 0)
            .order_by(MemoryRef.created_at.desc())
            .limit(limit)
        )
        refs = result.scalars().all()
        return [
            {
                "id": ref.chroma_id,
                "title": ref.title,
                "tags": ref.tags,
                "importance": ref.importance,
                "access_count": ref.access_count,
                "source_type": ref.source_type,
                "created_at": ref.created_at.isoformat() if ref.created_at else None,
            }
            for ref in refs
        ]

    async def update_access_count(self, chroma_id: str):
        """更新记忆访问次数"""
        await self.db.execute(
            update(MemoryRef)
            .where(MemoryRef.chroma_id == chroma_id)
            .values(
                access_count=MemoryRef.access_count + 1,
                last_accessed=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()
