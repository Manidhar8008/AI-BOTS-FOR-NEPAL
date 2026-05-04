# Qdrant Collection Schema

Collection name: `tenant_documents`

The collection is shared across tenants to simplify operations, but every point contains a required `tenant_id` payload and all reads/writes must filter by tenant.

## Vectors

| Name | Kind | Purpose |
| --- | --- | --- |
| `text_dense` | dense vector | Semantic retrieval for paraphrases and natural-language questions. |
| `text_sparse` | sparse vector | Keyword/BM25-style retrieval with IDF weighting for acts, dates, notice numbers, forms, and exact government terms. |

## Payload Indexes

Create keyword/integer/datetime payload indexes for:

```text
tenant_id
source_url
doc_type
scrape_job_id
document_id
chunk_id
language
created_at
date_scraped
chunk_index
```

`tenant_id` is the most important index. Without it, large government collections become slow and unsafe to query.

## Point ID Strategy

Use deterministic UUIDv5 point IDs:

```text
uuid5(namespace = tenant_id, name = source_url + "#" + chunk_index + ":" + content_hash)
```

This makes re-ingestion idempotent: unchanged chunks overwrite the same point instead of duplicating vectors.
