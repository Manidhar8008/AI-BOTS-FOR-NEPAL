from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings shared by API routes and workers."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://chatbot_admin:chatbot_admin_password@localhost:5432/chatbot_saas",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    qdrant_url: AnyHttpUrl = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="tenant_documents", alias="QDRANT_COLLECTION")
    embedding_dimension: int = Field(default=1536, alias="EMBEDDING_DIMENSION")

    # Tighten this in production to the dashboard domain and approved client demo domains.
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="CORS_ORIGINS",
    )


@lru_cache
def get_settings() -> Settings:
    """Cache settings so dependency injection does not re-read env files repeatedly."""
    return Settings()


settings = get_settings()
