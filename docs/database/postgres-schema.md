# PostgreSQL Schema

PostgreSQL is the source of truth for tenants, scrape job state, API key metadata, and crawled-document bookkeeping. Vector chunks live in Qdrant, but relational tables track ingestion state and provide auditability.

## Core Tables

| Table | Purpose |
| --- | --- |
| `tenants` | One isolated client/site. Every downstream job, document, vector point, demo URL, and widget key maps back to a tenant. |
| `scrape_jobs` | Async ingestion lifecycle for a tenant URL. The Next.js dashboard polls this table through `/api/status` in Step 2. |
| `api_keys` | Hashed tenant/widget API credentials. Raw keys are shown once and never stored. |
| `scraped_documents` | Canonical source documents discovered during ingestion, used for de-duplication, audit trails, and recrawls. |

## Isolation Rules

Every tenant-scoped table has a `tenant_id` column and an index beginning with `tenant_id`. The API layer must always set or filter by the active tenant. The schema also enables PostgreSQL row-level security using the session variable `app.current_tenant_id` as a defense-in-depth guard for future non-superuser deployments.

## Status Flow

`scrape_jobs.status` supports the dashboard progress flow:

```text
queued -> running -> scraping -> downloading -> chunking -> embedding -> indexing -> ready
```

Failure or cancellation states are terminal:

```text
failed
canceled
```

See `infra/postgres/init/001_schema.sql` for the executable schema.
