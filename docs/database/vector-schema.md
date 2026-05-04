# Qdrant Vector Schema

The MVP uses one shared Qdrant collection named `tenant_documents`. Tenant isolation is enforced by mandatory payload filters, not by trusting client input.

## Collection

```text
collection: tenant_documents
dense vector: text_dense, cosine distance, size from EMBEDDING_DIMENSION
sparse vector: text_sparse, BM25/SPLADE-style keyword vector
```

## Required Payload

Each point represents one text chunk and must include:

| Field | Type | Why it matters |
| --- | --- | --- |
| `tenant_id` | keyword | Mandatory isolation filter for every query. |
| `source_url` | keyword | Citation, source traceability, re-index targeting. |
| `doc_type` | keyword | Distinguishes `html`, `pdf`, and future document types. |
| `scrape_job_id` | keyword | Links vectors back to a specific ingestion run. |
| `document_id` | keyword | Links chunks back to canonical source documents. |
| `chunk_id` | keyword | Stable chunk identifier for dedupe and updates. |
| `chunk_index` | integer | Preserves source order for answer reconstruction. |
| `title` | text | Improves UX and keyword retrieval. |
| `text` | text | The retrieved context sent to the LLM. |
| `language` | keyword | Enables Nepali/English routing later. |
| `created_at` | datetime | Audit and freshness filtering. |

## Hybrid Retrieval Contract

All retrieval in Step 3 must use:

```text
tenant_id == requested_tenant_id
AND top_k dense semantic matches
AND top_k sparse keyword/BM25 matches
```

Results are merged/reranked server-side, then the top 5 chunks are passed to the LLM prompt with `source_url` citations.
