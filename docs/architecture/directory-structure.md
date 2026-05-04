# Directory Structure

This repository is organized as a small monorepo so the SaaS dashboard, API, ingestion worker, and infrastructure can evolve independently.

```text
.
├── apps/
│   ├── api/                         # FastAPI backend and ingestion/query orchestration
│   │   ├── app/
│   │   │   ├── api/routes/           # HTTP route modules: health now, ingest/chat in Steps 2-3
│   │   │   ├── core/                 # Settings, logging, security primitives
│   │   │   ├── db/                   # SQLAlchemy models and async Postgres session
│   │   │   ├── services/             # Scraping, chunking, embeddings, jobs, retrieval
│   │   │   ├── vector/               # Qdrant collection schema and tenant filter helpers
│   │   │   └── main.py               # FastAPI application factory
│   │   ├── tests/                    # Backend tests
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── web/                         # Next.js 14 App Router dashboard/demo/widget shell
│       ├── app/                      # App Router pages and global styles
│       ├── components/               # Shadcn UI and product components
│       ├── lib/                      # API client and shared frontend utilities
│       ├── public/                   # Static widget assets in Step 4
│       ├── Dockerfile
│       └── package.json
├── docs/
│   ├── architecture/                 # Product and system structure notes
│   └── database/                     # Relational + vector schema docs
├── infra/
│   ├── postgres/init/                # Local Postgres bootstrap SQL
│   └── qdrant/                       # Vector collection design notes
├── docker-compose.yml                # Local Postgres, Qdrant, Redis, optional API/web services
└── .env.example                      # Safe local environment template
```

The existing root `app/` folder is preserved as a legacy CLI prototype. New MVP work should happen under `apps/api` and `apps/web`.
