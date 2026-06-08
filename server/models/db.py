"""SQLAlchemy 数据模型"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, Text, Float, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(500), nullable=True)
    summary = Column(Text, nullable=True)
    tags = Column(ARRAY(String), default=[])
    message_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user / assistant / system / tool
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MemoryRef(Base):
    """记忆引用表 —— 关联 ChromaDB 向量与结构化元数据"""
    __tablename__ = "memory_refs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    chroma_id = Column(String(255), nullable=False, index=True)
    collection = Column(String(100), nullable=False)  # memories / conversation_chunks / knowledge_snippets
    title = Column(String(500), nullable=True)
    tags = Column(ARRAY(String), default=[])
    importance = Column(Float, default=0.5)
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime(timezone=True), nullable=True)
    source_type = Column(String(50), nullable=False)  # extracted / manual / search_result / conversation_summary
    source_conversation_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    query = Column(Text, nullable=False)
    results = Column(JSONB, default=[])
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
