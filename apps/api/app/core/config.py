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
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    dense_embedding_model: str = Field(default="text-embedding-3-small", alias="DENSE_EMBEDDING_MODEL")
    sparse_embedding_model: str = Field(
        default="Qdrant/bm25",
        alias="SPARSE_EMBEDDING_MODEL",
    )

    # MVP crawl guardrails. Government websites can be enormous, so ingestion must
    # stay bounded until we add durable queues, robots policy controls, and quotas.
    max_crawl_pages: int = Field(default=50, alias="MAX_CRAWL_PAGES")
    max_crawl_depth: int = Field(default=2, alias="MAX_CRAWL_DEPTH")
    crawl_timeout_seconds: float = Field(default=20.0, alias="CRAWL_TIMEOUT_SECONDS")
    crawl_user_agent: str = Field(
        default="GovChatbotSaaSBot/0.1 (+https://example.com/bot)",
        alias="CRAWL_USER_AGENT",
    )

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
