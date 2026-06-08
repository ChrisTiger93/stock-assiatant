"""
记忆管理 REST API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from api.deps import get_db, verify_api_key
from memory.manager import MemoryManager

router = APIRouter(dependencies=[Depends(verify_api_key)])


class ManualMemory(BaseModel):
    content: str
    tags: list[str] = []
    importance: float = 0.7


class MemoryResponse(BaseModel):
    id: str
    title: str | None
    tags: list[str]
    importance: float
    access_count: int
    source_type: str
    created_at: str | None


@router.get("/api/memories", response_model=list[MemoryResponse])
async def list_memories(
    collection: str = "memories",
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """获取记忆列表"""
    manager = MemoryManager(db)
    memories = await manager.list_memories(collection=collection, limit=limit)
    return [MemoryResponse(**m) for m in memories]


@router.post("/api/memories")
async def add_memory(
    body: ManualMemory,
    db: AsyncSession = Depends(get_db),
):
    """手动添加一条长期记忆"""
    manager = MemoryManager(db)
    from memory.store import vector_store

    from uuid import uuid4

    chroma_id = f"mem_manual_{uuid4().hex[:12]}"
    await vector_store.add(
        collection="memories",
        documents=[body.content],
        metadatas=[{
            "tags": ",".join(body.tags),
            "importance": body.importance,
            "source_type": "manual",
            "created_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }],
        ids=[chroma_id],
    )
    from models.db import MemoryRef

    ref = MemoryRef(
        id=uuid4(),
        chroma_id=chroma_id,
        collection="memories",
        title=body.content[:100],
        tags=body.tags,
        importance=body.importance,
        source_type="manual",
    )
    db.add(ref)
    await db.commit()
    return {"id": chroma_id, "status": "created"}


@router.delete("/api/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    collection: str = "memories",
    db: AsyncSession = Depends(get_db),
):
    """删除一条记忆"""
    manager = MemoryManager(db)
    await manager.delete_memory(memory_id, collection=collection)
    return {"status": "deleted"}
