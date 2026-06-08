"""
AI Assistant 服务端入口
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import settings
from api import chat_router, conversations_router, memories_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化服务"""
    logger.info("Starting AI Assistant server...")
    logger.info(f"Chat model: {settings.chat_model}")
    logger.info(f"Embedding model: {settings.embedding_model}")

    # 尝试初始化数据库（非阻塞，失败只警告）
    try:
        from api.deps import _get_engine
        from models.db import Base
        eng = _get_engine()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ensured")
        app.state.db_available = True
    except Exception as e:
        logger.warning(f"Database unavailable: {e}")
        logger.warning("Server will run without conversation persistence")
        app.state.db_available = False

    # ChromaDB 向量存储（嵌入式，始终可用）
    try:
        from memory.store import vector_store
        _ = vector_store  # 触发初始化
        logger.info("Vector store ready")
        app.state.vector_available = True
    except Exception as e:
        logger.error(f"Vector store unavailable: {e}")
        app.state.vector_available = False

    yield

    # 关闭连接
    try:
        from api.deps import _get_engine
        eng = _get_engine()
        await eng.dispose()
    except Exception:
        pass
    logger.info("Server shut down")


app = FastAPI(
    title="AI Assistant",
    description="AI 助理服务端 —— 多轮对话、长短期记忆、网络搜索",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(memories_router)


@app.get("/api/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "version": "0.1.0",
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "db_available": getattr(app.state, "db_available", False),
        "vector_available": getattr(app.state, "vector_available", False),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
