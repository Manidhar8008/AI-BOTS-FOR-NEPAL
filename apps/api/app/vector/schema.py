from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import settings


DENSE_VECTOR_NAME = "text_dense"
SPARSE_VECTOR_NAME = "text_sparse"


@dataclass(frozen=True)
class VectorPayloadField:
    """A payload field that should be indexed for fast filtered retrieval."""

    name: str
    schema: models.PayloadSchemaType


PAYLOAD_INDEXES: tuple[VectorPayloadField, ...] = (
    VectorPayloadField("tenant_id", models.PayloadSchemaType.KEYWORD),
    VectorPayloadField("source_url", models.PayloadSchemaType.KEYWORD),
    VectorPayloadField("doc_type", models.PayloadSchemaType.KEYWORD),
    VectorPayloadField("scrape_job_id", models.PayloadSchemaType.KEYWORD),
    VectorPayloadField("document_id", models.PayloadSchemaType.KEYWORD),
    VectorPayloadField("chunk_id", models.PayloadSchemaType.KEYWORD),
    VectorPayloadField("language", models.PayloadSchemaType.KEYWORD),
    VectorPayloadField("created_at", models.PayloadSchemaType.DATETIME),
    VectorPayloadField("chunk_index", models.PayloadSchemaType.INTEGER),
)


def tenant_filter(tenant_id: str) -> models.Filter:
    """Return the mandatory isolation filter for every vector read.

    Query code must compose additional filters with this filter rather than replacing it.
    """
    return models.Filter(
        must=[
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=tenant_id),
            )
        ]
    )


async def ensure_collection(client: AsyncQdrantClient) -> None:
    """Create the hybrid vector collection and payload indexes if needed."""
    collection_name = settings.qdrant_collection

    exists = await client.collection_exists(collection_name=collection_name)
    if not exists:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=settings.embedding_dimension,
                    distance=models.Distance.COSINE,
                    on_disk=True,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False)
                )
            },
        )

    for field in PAYLOAD_INDEXES:
        await client.create_payload_index(
            collection_name=collection_name,
            field_name=field.name,
            field_schema=field.schema,
        )
