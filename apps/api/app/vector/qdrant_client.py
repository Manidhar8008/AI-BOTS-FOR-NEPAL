from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastembed import SparseTextEmbedding
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import settings
from app.services.scraper import CrawledDocument
from app.vector.schema import DENSE_VECTOR_NAME, PAYLOAD_INDEXES, SPARSE_VECTOR_NAME


@dataclass(frozen=True)
class VectorChunk:
    """One tenant-scoped chunk ready for dense+sparse indexing."""

    point_id: str
    text: str
    payload: dict[str, object]


class QdrantHybridIndexer:
    """Creates a tenant-safe hybrid Qdrant index and inserts document chunks.

    Dense vectors are generated with OpenAI `text-embedding-3-small` by default.
    Sparse vectors use FastEmbed's BM25 model, giving exact keyword recall for
    government act names, dates, notice numbers, and form names.
    """

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        self.client = client or AsyncQdrantClient(url=str(settings.qdrant_url))
        self.collection_name = settings.qdrant_collection
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200,
            chunk_overlap=180,
            separators=[
                "\n\n",
                "\n",
                "। ",
                ". ",
                "? ",
                "! ",
                "; ",
                ", ",
                " ",
                "",
            ],
        )
        self._dense_embeddings: OpenAIEmbeddings | None = None
        self._sparse_embeddings: SparseTextEmbedding | None = None

    def build_chunks(
        self,
        *,
        tenant_id: str,
        scrape_job_id: str,
        documents: list[CrawledDocument],
    ) -> list[VectorChunk]:
        """Split source documents into semantically safer chunks with metadata.

        The required metadata fields are top-level Qdrant payload keys. This is
        intentional: tenant filters must not depend on nested metadata paths.
        """
        tenant_uuid = uuid.UUID(tenant_id)
        date_scraped = datetime.now(UTC).isoformat()
        chunks: list[VectorChunk] = []

        for document in documents:
            document_id = str(uuid.uuid5(tenant_uuid, document.source_url))
            split_texts = self._splitter.split_text(document.text)

            for chunk_index, chunk_text in enumerate(split_texts):
                normalized_chunk = chunk_text.strip()
                if not normalized_chunk:
                    continue

                chunk_hash = hashlib.sha256(normalized_chunk.encode("utf-8")).hexdigest()
                point_id = str(
                    uuid.uuid5(
                        tenant_uuid,
                        f"{document.source_url}#{chunk_index}:{chunk_hash}",
                    )
                )

                payload: dict[str, object] = {
                    # Critical isolation/citation metadata required by Step 2.
                    "tenant_id": tenant_id,
                    "source_url": document.source_url,
                    "doc_type": document.doc_type,
                    "date_scraped": date_scraped,
                    # Additional retrieval/audit metadata used by Step 3+.
                    "created_at": date_scraped,
                    "scrape_job_id": scrape_job_id,
                    "document_id": document_id,
                    "chunk_id": point_id,
                    "chunk_index": chunk_index,
                    "title": document.title or "",
                    "text": normalized_chunk,
                    "content_hash": chunk_hash,
                    "language": document.metadata.get("language") or "unknown",
                    "metadata": document.metadata,
                }

                chunks.append(VectorChunk(point_id=point_id, text=normalized_chunk, payload=payload))

        return chunks

    async def upsert_chunks(self, chunks: list[VectorChunk], *, batch_size: int = 64) -> int:
        """Embed and upsert chunks into Qdrant with dense+sparse vectors."""
        if not chunks:
            return 0

        texts = [chunk.text for chunk in chunks]
        dense_vectors = await self._embed_dense(texts)
        sparse_vectors = await self._embed_sparse(texts)

        if len(dense_vectors) != len(chunks) or len(sparse_vectors) != len(chunks):
            raise RuntimeError("Embedding count mismatch while preparing Qdrant upsert.")

        await self.ensure_hybrid_collection(dense_vector_size=len(dense_vectors[0]))

        indexed_count = 0
        for start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[start : start + batch_size]
            batch_dense = dense_vectors[start : start + batch_size]
            batch_sparse = sparse_vectors[start : start + batch_size]

            points = [
                models.PointStruct(
                    id=chunk.point_id,
                    vector={
                        DENSE_VECTOR_NAME: dense,
                        SPARSE_VECTOR_NAME: sparse,
                    },
                    payload=chunk.payload,
                )
                for chunk, dense, sparse in zip(batch_chunks, batch_dense, batch_sparse, strict=True)
            ]

            await self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            indexed_count += len(points)

        return indexed_count

    async def ensure_hybrid_collection(self, *, dense_vector_size: int) -> None:
        """Create the hybrid collection and payload indexes idempotently."""
        exists = await self.client.collection_exists(collection_name=self.collection_name)
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: models.VectorParams(
                        size=dense_vector_size,
                        distance=models.Distance.COSINE,
                        on_disk=True,
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=False),
                        modifier=models.Modifier.IDF,
                    )
                },
            )

        for field in PAYLOAD_INDEXES:
            try:
                await self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field.name,
                    field_schema=field.schema,
                    wait=True,
                )
            except Exception as exc:
                # Qdrant treats existing indexes as errors on some versions.
                # Re-raising unrelated errors keeps startup failures visible.
                if "already exists" not in str(exc).lower():
                    raise

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Generate dense semantic embeddings.

        We fail fast when the OpenAI key is missing because silently switching
        dense models can corrupt an existing collection with the wrong dimension.
        """
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for dense embeddings. "
                "Set it in the API environment before running ingestion."
            )

        if self._dense_embeddings is None:
            self._dense_embeddings = OpenAIEmbeddings(
                model=settings.dense_embedding_model,
                openai_api_key=settings.openai_api_key,
            )

        return await self._dense_embeddings.aembed_documents(texts)

    async def _embed_sparse(self, texts: list[str]) -> list[models.SparseVector]:
        """Generate sparse BM25 vectors for exact keyword matching."""
        if self._sparse_embeddings is None:
            self._sparse_embeddings = SparseTextEmbedding(model_name=settings.sparse_embedding_model)

        sparse_embeddings = await asyncio.to_thread(lambda: list(self._sparse_embeddings.embed(texts)))

        return [
            models.SparseVector(
                indices=self._to_python_list(embedding.indices),
                values=self._to_python_list(embedding.values),
            )
            for embedding in sparse_embeddings
        ]

    @staticmethod
    def _to_python_list(value: object) -> list:
        """Convert numpy arrays or native lists into JSON-serializable lists."""
        if hasattr(value, "tolist"):
            return value.tolist()
        return list(value)  # type: ignore[arg-type]
