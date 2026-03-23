"""
Application settings loaded from environment variables.
Uses pydantic-settings for validation and type coercion.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Centralized configuration for the RTV ML system."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    # Judge: separate LLM call to avoid self-evaluation bias (design doc Section 7)
    judge_model: str = "claude-sonnet-4-20250514"

    # --- Observability (LangSmith) ---
    langchain_api_key: str = ""
    langsmith_project: str = "rtv-multi-agent-system"

    # --- Database ---
    duckdb_path: str = "data/rtv_households.duckdb"

    # --- Vector Store (Qdrant) ---
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "rtv_handbook"
    embedding_model: str = "all-MiniLM-L6-v2"

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # --- Object Storage (MinIO / S3) ---
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "rtv-artifacts"

    # --- Tracing ---
    otel_endpoint: str = "http://localhost:4317"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    log_level: str = "INFO"

    # --- RAG ---
    chunk_size: int = 900
    chunk_overlap: int = 180
    top_k: int = 5
    rerank_top_k: int = 3

    @property
    def duckdb_abs_path(self) -> Path:
        p = Path(self.duckdb_path)
        if not p.is_absolute():
            return PROJECT_ROOT / p
        return p

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def minio_url(self) -> str:
        return f"http://{self.minio_endpoint}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
