from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    embedding_provider: str = "hash"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 384
    knowledge_path: Path = Path("knowledge/sounderone_knowledge.json")
    knowledge_min_score: float = 0.48
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_path: Path | None = None
    qdrant_collection: str = "sounderone_knowledge"
    rag_rebuild_on_startup: bool = True
    webhook_secret: str | None = "change-me"
    admin_api_key: str = "change-me-admin"
    business_timezone: str = "Asia/Shanghai"
    business_hours_start: str = "09:00"
    business_hours_end: str = "22:00"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
