-- Step 1 relational schema for the multi-tenant AI chatbot SaaS.
--
-- This file is mounted into the Postgres container and runs automatically
-- the first time the local database volume is created.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Explicit enums make job transitions and tenant state easy to validate.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tenant_status') THEN
    CREATE TYPE tenant_status AS ENUM ('active', 'paused', 'archived');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scrape_job_status') THEN
    CREATE TYPE scrape_job_status AS ENUM (
      'queued',
      'running',
      'scraping',
      'downloading',
      'chunking',
      'embedding',
      'indexing',
      'ready',
      'failed',
      'canceled'
    );
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'api_key_status') THEN
    CREATE TYPE api_key_status AS ENUM ('active', 'revoked', 'expired');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'document_type') THEN
    CREATE TYPE document_type AS ENUM ('html', 'pdf', 'text', 'unknown');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Human-readable identifier used in demo URLs such as /demo/kathmandu-metro.
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  root_url TEXT NOT NULL,
  status tenant_status NOT NULL DEFAULT 'active',
  -- Public, non-secret widget identifier. Private auth uses api_keys.
  public_widget_key TEXT NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
  -- Flexible plan/features metadata without requiring migrations for every MVP toggle.
  settings JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at TIMESTAMPTZ
);

COMMENT ON TABLE tenants IS 'One isolated client website. All relational records and vector payloads must map back to a tenant.';
COMMENT ON COLUMN tenants.public_widget_key IS 'Non-secret key used to identify the widget/demo tenant; never grants data access by itself.';

CREATE TABLE IF NOT EXISTS scrape_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  target_url TEXT NOT NULL,
  status scrape_job_status NOT NULL DEFAULT 'queued',
  -- Stage is intentionally separate from status so the UI can show friendly progress text.
  stage TEXT NOT NULL DEFAULT 'queued',
  progress_current INTEGER NOT NULL DEFAULT 0 CHECK (progress_current >= 0),
  progress_total INTEGER NOT NULL DEFAULT 0 CHECK (progress_total >= 0),
  discovered_url_count INTEGER NOT NULL DEFAULT 0 CHECK (discovered_url_count >= 0),
  processed_document_count INTEGER NOT NULL DEFAULT 0 CHECK (processed_document_count >= 0),
  failed_url_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_url_count >= 0),
  -- Store structured error/debug details without exposing them to the public widget.
  error JSONB,
  requested_by TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE scrape_jobs IS 'Async ingestion job state used by the dashboard polling/status endpoint.';
COMMENT ON COLUMN scrape_jobs.status IS 'Machine-readable job state. Dashboard labels should be derived from this plus stage/progress.';

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_tenant_created
  ON scrape_jobs (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scrape_jobs_status_created
  ON scrape_jobs (status, created_at);

CREATE TABLE IF NOT EXISTS api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  -- Store a short public prefix for operator support; never use it as a secret.
  key_prefix TEXT NOT NULL,
  -- Store only a salted/peppered hash of the raw API key.
  key_hash TEXT NOT NULL UNIQUE,
  scopes TEXT[] NOT NULL DEFAULT ARRAY['widget:chat'],
  status api_key_status NOT NULL DEFAULT 'active',
  last_used_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ
);

COMMENT ON TABLE api_keys IS 'Hashed tenant API credentials for widget/demo/API access. Raw secrets are shown once and never stored.';
COMMENT ON COLUMN api_keys.scopes IS 'Least-privilege permissions such as widget:chat, ingest:write, or admin:read.';

CREATE INDEX IF NOT EXISTS idx_api_keys_tenant_status
  ON api_keys (tenant_id, status);

CREATE TABLE IF NOT EXISTS scraped_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  scrape_job_id UUID REFERENCES scrape_jobs(id) ON DELETE SET NULL,
  source_url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  doc_type document_type NOT NULL DEFAULT 'unknown',
  title TEXT,
  content_hash TEXT,
  http_status INTEGER,
  byte_size BIGINT CHECK (byte_size IS NULL OR byte_size >= 0),
  language TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  fetched_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, canonical_url)
);

COMMENT ON TABLE scraped_documents IS 'Canonical crawl inventory for dedupe, audit, re-indexing, and source-level troubleshooting.';
COMMENT ON COLUMN scraped_documents.metadata IS 'Crawler metadata such as content-type, PDF page count, crawl depth, and discovered parent URL.';

CREATE INDEX IF NOT EXISTS idx_scraped_documents_tenant_type
  ON scraped_documents (tenant_id, doc_type);

CREATE INDEX IF NOT EXISTS idx_scraped_documents_job
  ON scraped_documents (scrape_job_id);

-- Keep updated_at current without requiring application code in every write path.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tenants_updated_at ON tenants;
CREATE TRIGGER trg_tenants_updated_at
BEFORE UPDATE ON tenants
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_scrape_jobs_updated_at ON scrape_jobs;
CREATE TRIGGER trg_scrape_jobs_updated_at
BEFORE UPDATE ON scrape_jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_scraped_documents_updated_at ON scraped_documents;
CREATE TRIGGER trg_scraped_documents_updated_at
BEFORE UPDATE ON scraped_documents
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Defense in depth for future production roles.
-- FastAPI should set app.current_tenant_id for tenant-scoped requests before querying.
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE scraped_documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_tenants ON tenants;
CREATE POLICY tenant_isolation_tenants ON tenants
  USING (id::text = current_setting('app.current_tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation_scrape_jobs ON scrape_jobs;
CREATE POLICY tenant_isolation_scrape_jobs ON scrape_jobs
  USING (tenant_id::text = current_setting('app.current_tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation_api_keys ON api_keys;
CREATE POLICY tenant_isolation_api_keys ON api_keys
  USING (tenant_id::text = current_setting('app.current_tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation_scraped_documents ON scraped_documents;
CREATE POLICY tenant_isolation_scraped_documents ON scraped_documents
  USING (tenant_id::text = current_setting('app.current_tenant_id', true));
