"""
会话管理 REST API
"""
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from models.db import Conversation, Message
from api.deps import get_db, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _uuid(v: str):
    try: return UUID(v)
    except: return v


class ConversationCreate(BaseModel):
    title: str | None = None

class ConversationResponse(BaseModel):
    id: str; title: str | None; summary: str | None
    tags: list[str]; message_count: int
    created_at: str | None; updated_at: str | None

class MessageResponse(BaseModel):
    id: str; role: str; content: str; metadata: dict
    created_at: str | None


@router.post("/api/conversations", response_model=ConversationResponse)
async def create_conversation(
    body: ConversationCreate = ConversationCreate(),
    db: AsyncSession = Depends(get_db)):
    conv = Conversation(id=uuid4(), title=body.title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return _cr(conv)

@router.get("/api/conversations", response_model=list[ConversationResponse])
async def list_conversations(limit: int = 20, offset: int = 0,
    db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
        .offset(offset).limit(limit))
    return [_cr(c) for c in r.scalars().all()]

@router.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(Conversation).where(Conversation.id == _uuid(conversation_id)))
    c = r.scalar_one_or_none()
    if not c: raise HTTPException(404, "Not found")
    return _cr(c)

@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    cid = _uuid(conversation_id)
    r = await db.execute(select(Conversation).where(Conversation.id == cid))
    c = r.scalar_one_or_none()
    if not c: raise HTTPException(404, "Not found")
    await db.execute(delete(Message).where(Message.conversation_id == cid))
    await db.delete(c)
    await db.commit()
    return {"status": "deleted"}

@router.get("/api/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(conversation_id: str, limit: int = 100,
    db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        text("SELECT id, role, content, metadata, created_at FROM messages "
             "WHERE conversation_id = :cid ORDER BY created_at LIMIT :lim"),
        {"cid": str(_uuid(conversation_id)), "lim": limit})
    msgs = []
    for row in r.fetchall():
        msgs.append(MessageResponse(
            id=str(row[0]), role=row[1], content=row[2],
            metadata=row[3] or {},
            created_at=row[4].isoformat() if row[4] else None))
    return msgs

def _cr(c): return ConversationResponse(
    id=str(c.id), title=c.title, summary=c.summary,
    tags=c.tags or [], message_count=c.message_count or 0,
    created_at=c.created_at.isoformat() if c.created_at else None,
    updated_at=c.updated_at.isoformat() if c.updated_at else None)
