"""
FastAPI 依赖项 —— 数据库会话、认证
"""
from typing import AsyncGenerator

from fastapi import Header, HTTPException

from config import settings

# 异步引擎（延迟连接，首次使用时才连数据库）
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


# session factory
_async_session_factory = None


def async_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        eng = _get_engine()
        _async_session_factory = async_sessionmaker(
            eng,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory()


async def get_db() -> AsyncGenerator:
    """FastAPI 依赖：获取数据库会话"""
    try:
        session = async_session_factory()
        async with session as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Please check PostgreSQL is running.",
        )


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """验证 API Key"""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
