from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, ingest
from app.core.config import settings


def create_app() -> FastAPI:
    """Create the API application.

    Keeping app construction in a factory makes tests and future worker bootstraps
    cleaner because they can import the same configured application.
    """
    app = FastAPI(
        title="Government Chatbot SaaS API",
        version="0.1.0",
        description="Multi-tenant ingestion and hybrid RAG API for large government websites.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(ingest.router, prefix="/api", tags=["ingestion"])
    return app


app = create_app()
