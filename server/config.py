"""
配置管理 —— 从 .env 文件和环境变量加载配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


class Settings:
    # --- AI 服务 ---
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")

    # --- 搜索 ---
    searxng_base_url: str = os.getenv("SEARXNG_BASE_URL", "http://searxng:8080")
    bing_search_api_key: str = os.getenv("BING_SEARCH_API_KEY", "")
    serpapi_api_key: str = os.getenv("SERPAPI_API_KEY", "")

    # --- 金融数据 ---
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")

    # --- 数据库 ---
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "ai_assistant")
    postgres_user: str = os.getenv("POSTGRES_USER", "assistant")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # --- Redis ---
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- ChromaDB ---
    chroma_persist_dir: str = os.getenv(
        "CHROMA_PERSIST_DIR",
        str(Path(__file__).parent.parent / "data" / "chromadb"),
    )

    # --- 服务 ---
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    api_key: str = os.getenv("API_KEY", "")

    # --- 模型 ---
    chat_model: str = os.getenv("CHAT_MODEL", "deepseek-chat")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v2")

    # --- TTS ---
    tts_model: str = os.getenv("TTS_MODEL", "cosyvoice-v3-flash")
    tts_voice: str = os.getenv("TTS_VOICE", "longanyang")
    tts_sample_rate: int = int(os.getenv("TTS_SAMPLE_RATE", "24000"))
    tts_enabled: bool = os.getenv("TTS_ENABLED", "true").lower() == "true"

    # --- 记忆 ---
    memory_top_k: int = int(os.getenv("MEMORY_TOP_K", "5"))
    short_term_turns: int = int(os.getenv("SHORT_TERM_TURNS", "20"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))


settings = Settings()
