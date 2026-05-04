from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ScrapeJob, ScrapeJobStatus, ScrapedDocument, Tenant
from app.db.session import AsyncSessionLocal, get_db_session
from app.services.scraper import CrawledDocument, GovernmentSiteScraper
from app.vector.qdrant_client import QdrantHybridIndexer

logger = logging.getLogger(__name__)
router = APIRouter()


class IngestRequest(BaseModel):
    """Request body for kicking off an async crawl/index job."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://example.gov.np",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }
    )

    url: AnyHttpUrl
    tenant_id: uuid.UUID


class IngestAcceptedResponse(BaseModel):
    """202 response returned immediately so the dashboard never hangs."""

    job_id: uuid.UUID
    tenant_id: uuid.UUID
    status: ScrapeJobStatus
    status_url: str


class JobStatusResponse(BaseModel):
    """Tenant-scoped job status for dashboard polling."""

    job_id: uuid.UUID
    tenant_id: uuid.UUID
    status: ScrapeJobStatus
    stage: str
    progress_current: int
    progress_total: int
    discovered_url_count: int
    processed_document_count: int
    failed_url_count: int
    error: dict | None


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestAcceptedResponse,
    summary="Start an async tenant website ingestion job",
)
async def ingest_url(
    payload: IngestRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IngestAcceptedResponse:
    """Create a scrape job and process it in the background.

    The request returns as soon as the job row is committed. The heavy crawl,
    PDF parsing, chunking, embedding, and Qdrant writes happen after the response.
    """
    tenant = await session.scalar(select(Tenant).where(Tenant.id == payload.tenant_id))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found. Create the tenant before starting ingestion.",
        )

    job = ScrapeJob(
        tenant_id=payload.tenant_id,
        target_url=str(payload.url),
        status=ScrapeJobStatus.QUEUED,
        stage="queued",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    background_tasks.add_task(
        process_ingestion_job,
        job_id=job.id,
        tenant_id=payload.tenant_id,
        target_url=str(payload.url),
    )

    return IngestAcceptedResponse(
        job_id=job.id,
        tenant_id=payload.tenant_id,
        status=ScrapeJobStatus.QUEUED,
        status_url=f"/api/status/{job.id}?tenant_id={payload.tenant_id}",
    )


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll a tenant-scoped ingestion job",
)
async def get_ingestion_status(
    job_id: uuid.UUID,
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobStatusResponse:
    """Return job progress while enforcing tenant_id in the lookup."""
    job = await session.scalar(
        select(ScrapeJob).where(ScrapeJob.id == job_id, ScrapeJob.tenant_id == tenant_id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    return JobStatusResponse(
        job_id=job.id,
        tenant_id=job.tenant_id,
        status=job.status,
        stage=job.stage,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        discovered_url_count=job.discovered_url_count,
        processed_document_count=job.processed_document_count,
        failed_url_count=job.failed_url_count,
        error=job.error,
    )


async def process_ingestion_job(*, job_id: uuid.UUID, tenant_id: uuid.UUID, target_url: str) -> None:
    """Background ingestion worker for the MVP.

    FastAPI BackgroundTasks are process-local and intentionally simple. The
    database status updates below are written so this function can move to
    Celery/RQ/Arq later without changing the public `/api/ingest` contract.
    """
    scraper = GovernmentSiteScraper()
    indexer = QdrantHybridIndexer()

    async with AsyncSessionLocal() as session:
        try:
            await _update_job(
                session,
                job_id,
                status=ScrapeJobStatus.RUNNING,
                stage="starting",
                started_at=_utc_now(),
            )

            await _update_job(session, job_id, status=ScrapeJobStatus.SCRAPING, stage="scraping")
            crawl_result = await scraper.crawl(target_url)

            if not crawl_result.documents:
                raise RuntimeError("No crawlable HTML or PDF content was extracted.")

            await _store_scraped_documents(
                session=session,
                tenant_id=tenant_id,
                job_id=job_id,
                documents=crawl_result.documents,
            )

            await _update_job(
                session,
                job_id,
                status=ScrapeJobStatus.CHUNKING,
                stage="chunking",
                discovered_url_count=len(crawl_result.discovered_urls),
                processed_document_count=len(crawl_result.documents),
                failed_url_count=len(crawl_result.failed_urls),
            )
            chunks = indexer.build_chunks(
                tenant_id=str(tenant_id),
                scrape_job_id=str(job_id),
                documents=crawl_result.documents,
            )

            await _update_job(
                session,
                job_id,
                status=ScrapeJobStatus.EMBEDDING,
                stage="embedding",
                progress_current=0,
                progress_total=len(chunks),
            )

            await _update_job(session, job_id, status=ScrapeJobStatus.INDEXING, stage="indexing")
            indexed_count = await indexer.upsert_chunks(chunks)

            await _update_job(
                session,
                job_id,
                status=ScrapeJobStatus.READY,
                stage="ready",
                progress_current=indexed_count,
                progress_total=indexed_count,
                finished_at=_utc_now(),
            )
        except Exception as exc:
            await session.rollback()
            logger.exception("Ingestion job failed", extra={"job_id": str(job_id)})
            await _update_job(
                session,
                job_id,
                status=ScrapeJobStatus.FAILED,
                stage="failed",
                error={"type": type(exc).__name__, "message": str(exc)},
                finished_at=_utc_now(),
            )


async def _store_scraped_documents(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    documents: list[CrawledDocument],
) -> None:
    """Upsert crawl inventory rows for auditability and recrawl de-duping."""
    now = _utc_now()
    table = ScrapedDocument.__table__

    for document in documents:
        document_metadata = {
            **document.metadata,
            "qdrant_collection": settings.qdrant_collection,
        }
        values = {
            "tenant_id": tenant_id,
            "scrape_job_id": job_id,
            "source_url": document.source_url,
            "canonical_url": document.source_url,
            "doc_type": document.doc_type,
            "title": document.title,
            "content_hash": document.content_hash,
            "http_status": document.http_status,
            "byte_size": document.byte_size,
            "language": document.metadata.get("language"),
            "metadata": document_metadata,
            "fetched_at": now,
            "updated_at": now,
        }
        insert_stmt = pg_insert(table).values(**values)
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[table.c.tenant_id, table.c.canonical_url],
            set_={
                "scrape_job_id": job_id,
                "source_url": document.source_url,
                "doc_type": document.doc_type,
                "title": document.title,
                "content_hash": document.content_hash,
                "http_status": document.http_status,
                "byte_size": document.byte_size,
                "language": document.metadata.get("language"),
                "metadata": document_metadata,
                "fetched_at": now,
                "updated_at": now,
            },
        )
        await session.execute(upsert_stmt)

    await session.commit()


async def _update_job(session: AsyncSession, job_id: uuid.UUID, **values: object) -> None:
    """Patch a scrape job status and commit immediately for polling UIs."""
    await session.execute(update(ScrapeJob).where(ScrapeJob.id == job_id).values(**values))
    await session.commit()


def _utc_now() -> datetime:
    return datetime.now(UTC)
