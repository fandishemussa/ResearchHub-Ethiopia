# ResearchHub Ethiopia

ResearchHub Ethiopia is an AI-assisted research information management platform for aggregating, normalizing, searching, and analysing scholarly output from Ethiopian universities.

It connects institutional repositories through OAI-PMH or validated file imports, preserves metadata provenance, supports semantic discovery with PostgreSQL and pgvector, and provides operational workflows for harvesting, import review, research intelligence, and repository health monitoring.

> **Project status:** active development. The architecture includes scalability and observability foundations, but no production-capacity claim—including support for 1,000 concurrent users—is made without repeatable load-test evidence on documented hardware.

## Start here

- **Run the platform:** [Quick start with Docker](#quick-start-with-docker)
- **Connect a university repository:** [Adding a research source](#adding-a-research-source)
- **Import an existing dataset:** [Importing metadata files](#importing-metadata-files)
- **Index downloaded PDFs:** [Full-text document indexing](#full-text-document-indexing)
- **Configure local AI:** [AI providers and Ollama](#ai-providers-and-ollama)
- **Develop and test:** [Development without Docker](#development-without-docker) and [Testing and quality checks](#testing-and-quality-checks)
- **Operate and diagnose:** [Health and observability](#health-and-observability), [Backup and recovery](#backup-and-recovery), and [Troubleshooting](#troubleshooting)
- **Understand delivery status:** [Feature maturity](#feature-maturity) and [Known limitations](#known-limitations)

## Feature maturity

The table separates working functionality from foundations and staged enhancements. “Implemented” means the code path exists; it does not by itself mean production hardening or capacity has been proven.

| Area                          | Status                 | Current capability                                                                                                                                                                |
| ----------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Managed sources               | Implemented            | Add, edit, test, enable, disable, remove/archive, and restore OAI-PMH sources                                                                                                     |
| Harvesting                    | Implemented            | Dry-run, full and incremental modes, checkpoints, retries, cancellation, events, failures, and progress                                                                           |
| Metadata imports              | Implemented            | XML, JSON, and CSV upload, validation preview, progress, confirmation, cancellation, and partial-row tolerance                                                                    |
| Catalogue                     | Implemented            | Universities, publications, authors, source provenance, details, filters, and dashboard summaries                                                                                 |
| Semantic discovery            | Implemented            | Publication embeddings, pgvector similarity search, explainable related-publication results                                                                                       |
| Full-text RAG foundation      | Implemented            | Registered PDFs, extraction, chunking, 384-dimensional chunk embeddings, secure document access, and chunk browsing                                                               |
| Research assistant            | Implemented            | Persistent conversations, independently collapsible side panels, scoped hybrid retrieval, grounded answers, rich citations, evidence inspection, follow-ups, feedback, and export |
| Research intelligence         | Implemented foundation | Summaries, keywords, formatted citations, duplicate candidates, and trend APIs; quality depends on available metadata/models                                                      |
| Authentication                | Security foundation    | Password/token/session primitives exist; public deployment still requires complete role enforcement and operational hardening                                                     |
| Observability                 | Implemented foundation | Health checks, structured logs, Prometheus metrics, Grafana provisioning, and load-test workloads                                                                                 |
| Comparison/workspace/admin UI | Planned                | Research comparison, saved collections, expanded indexing administration, and AI status interfaces remain staged                                                                  |

## Highlights

- **Repository aggregation:** managed OAI-PMH sources, DSpace-compatible metadata, full and incremental harvesting, resumption tokens, checkpoints, retries, cancellation, and job history.
- **Validated imports:** XML, JSON, and CSV uploads up to the configured limit, browser upload progress, preview-before-confirmation, tolerant row validation, and duplicate-file protection.
- **National research catalogue:** universities, repositories, publications, authors, journals, keywords, controlled vocabularies, provenance, and metadata history.
- **Research discovery:** faceted metadata search, pgvector semantic search, publication similarity, safe external links, deterministic result types, and publication details.
- **AI research intelligence:** grounded university-research assistant, summaries, keyword extraction, citation generation, duplicate candidates, and research trend APIs with local-first provider defaults.
- **Metadata quality:** configurable quality scoring, issue tracking, historical reports, and recalculation workflows.
- **Authentication foundation:** Argon2 password hashing, short-lived access tokens, rotating refresh sessions, token reuse detection, account lockout, recovery tokens, and Redis-backed authentication rate limits.
- **Concurrency controls:** PostgreSQL row/advisory locks, one-active-harvest protection, bounded request and connection pools, import confirmation locking, and safe Celery task cleanup.
- **Operations:** health/readiness endpoints, structured request logs, request/instance IDs, Prometheus metrics, Grafana, Nginx proxying, optional PgBouncer, isolated Celery queue profiles, and Locust workloads.
- **Modern frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS, TanStack Query, Recharts, responsive layouts, accessible loading/error states, and Docker-aware API proxying.

## Architecture

```text
Browser
  │
  ├── :3000 ── Next.js ── /backend-api/* ─┐
  │                                        │
  └── :8080 ── Nginx ──────────────────────┤
                                           ▼
                                    FastAPI replicas
                                      │    │    │
                         ┌────────────┘    │    └─────────────┐
                         ▼                 ▼                  ▼
               PostgreSQL + pgvector    Redis          Shared import storage
                         ▲                 ▲
                         └──── Celery workers + scheduler

Prometheus ──scrapes──> FastAPI /metrics ──visualized by──> Grafana
```

### Metadata and full-text pipeline

```text
Managed OAI-PMH source or validated file
  → harvest/import job
  → normalization and record validation
  → publication + provenance persistence
  → metadata quality checks
  → publication embedding
  → semantic search

Registered PDF
  → safe download/registration
  → text extraction
  → page-aware chunking
  → chunk embedding in pgvector
  → hybrid assistant retrieval
  → grounded answer with document/page/chunk citations
```

Every imported or harvested record retains its source identity. Full-text files are addressed through registered document UUIDs; normal API responses do not expose local filesystem paths or raw embeddings.

### Browser and Docker API routing

```text
Browser request: /backend-api/documents
       │
       ▼
Next.js rewrite (server-side only)
       │ INTERNAL_API_URL=http://api:8111
       ▼
FastAPI route: /api/documents
```

`api` is a Docker-network hostname and must never be used directly by browser JavaScript. Host tools use `http://localhost:8111`; browser code uses the same-origin `/backend-api` path.

Request-critical state is intended to remain outside API process memory:

- PostgreSQL stores durable application, authentication, job, and research data.
- Redis provides the Celery broker/result backend and short-lived distributed coordination.
- Mounted or object storage holds uploaded import files.
- Celery isolates harvesting and expensive AI/background workloads from interactive API traffic.

More detail is available in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/architecture/scalability.md](docs/architecture/scalability.md).

## Technology stack

| Layer           | Technology                                                                      |
| --------------- | ------------------------------------------------------------------------------- |
| Web application | Next.js 16, React 19, TypeScript, Tailwind CSS, TanStack Query                  |
| API             | Python 3.13, FastAPI, Pydantic 2                                                |
| Persistence     | SQLAlchemy 2 async, Alembic, PostgreSQL 17, pgvector                            |
| Background work | Celery, Redis                                                                   |
| Harvesting      | OAI-PMH, XML parsing, DSpace-oriented normalization                             |
| AI              | Sentence Transformers, PyTorch CPU, optional OpenAI-compatible/Ollama providers |
| Proxy/pooling   | Nginx, optional PgBouncer transaction pooling                                   |
| Observability   | structlog, Prometheus, Grafana                                                  |
| Testing         | pytest, Ruff, mypy, Vitest, Testing Library, ESLint, Locust                     |

## Repository layout

```text
ResearchHub-Ethiopia/
├── ai/                 Embeddings, semantic utilities, and AI provider contracts
├── backend/            FastAPI API, domain schemas, services, persistence, migrations
├── data/               Local harvested datasets and import summaries
├── docker/             Nginx, Prometheus, and Grafana configuration
├── docs/               Architecture, feature, performance, and operations guides
├── frontend/           Next.js application and frontend tests
├── harvester/          Connector framework, normalization, and harvesting engine
├── load-tests/         Locust workloads, fixtures, and report output
├── scripts/            Administration, import, and embedding utilities
├── tests/              Backend and harvester test suite
├── docker-compose.yml  Development and optional production-like profiles
├── pyproject.toml       Python dependencies and tooling
└── .env.example        Typed configuration reference
```

## Prerequisites

For the recommended Docker workflow:

- Docker Desktop with Docker Compose v2
- At least 8 GB RAM; more is recommended when loading local embedding models
- Git

For host-based development:

- Python 3.13
- Node.js 20 or newer
- PostgreSQL 17 with pgvector
- Redis 7

## Quick start with Docker

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
docker compose exec api alembic -c backend/alembic.ini upgrade head
docker compose ps
```

Open:

| Service                       | URL                                  |
| ----------------------------- | ------------------------------------ |
| Frontend development server   | <http://localhost:3000>              |
| Combined Nginx entry point    | <http://localhost:8080>              |
| API and OpenAPI documentation | <http://localhost:8111/docs>         |
| API readiness                 | <http://localhost:8111/health/ready> |
| Prometheus metrics            | <http://localhost:8111/metrics>      |

The browser uses `/backend-api/*`. Next.js rewrites those requests to `INTERNAL_API_URL=http://api:8111`, so Docker-internal hostnames are never exposed to browser code.

### Useful lifecycle commands

```powershell
docker compose logs -f api worker frontend
docker compose restart api
docker compose restart worker
docker compose restart frontend
docker compose down
```

Restart the worker after changing Celery task or persistence code; Celery does not hot-reload Python modules. Restart the frontend after changing `next.config.ts`.

## Database migrations

```powershell
docker compose exec api alembic -c backend/alembic.ini heads
docker compose exec api alembic -c backend/alembic.ini current
docker compose exec api alembic -c backend/alembic.ini upgrade head
```

Create a migration only after reviewing model and database differences:

```powershell
docker compose exec api alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
```

Never run destructive downgrade or reset commands against a database containing irreplaceable research data.

## Adding a research source

In the web application, open **Repositories → Add source**.

For an OAI-PMH endpoint such as:

```text
https://example.edu/oai/request?verb=ListRecords&metadataPrefix=oai_dc
```

enter:

```text
Source type:       OAI-PMH Repository
OAI-PMH endpoint:  https://example.edu/oai/request
Metadata prefix:   oai_dc
Set specification: leave blank to harvest every exposed set
```

Do not include `verb`, `metadataPrefix`, or pagination parameters in the saved endpoint. ResearchHub constructs protocol requests itself.

Available workflows include:

- **Test connection:** identify the repository and validate metadata-format support.
- **Dry run:** retrieve and normalize without importing confirmed research records.
- **Incremental harvest:** continue from the last successful harvest date.
- **Full harvest:** traverse all available records.
- **Disable:** retain configuration and history while preventing new jobs.
- **Remove:** hide/archive sources with history or physically remove unused sources.

One active harvest per source and a configurable global harvest capacity are enforced in the backend, not only in the UI.

## Importing metadata files

Repository pages accept `.json`, `.csv`, and `.xml` files. The workflow is:

1. Select a file.
2. Watch byte-level upload progress.
3. Review valid and skipped record counts.
4. Inspect sample records and validation warnings.
5. Confirm the database import.

JSON can be a top-level array or an object containing `records` or `items`. A minimal record is:

```json
{
  "external_id": "repository:item:123",
  "title": "Agricultural resilience in Ethiopia",
  "authors": ["Aster Bekele"],
  "publication_year": 2025,
  "abstract": "...",
  "subjects": ["Agriculture", "Climate resilience"],
  "landing_page_url": "https://repository.example.edu/items/123"
}
```

The importer also understands common DSpace metadata keys such as `name`, `dc.title`, `dc.contributor.author`, `dc.description.abstract`, `dc.date.issued`, `dc.subject`, and `dc.identifier.uri`. Invalid rows are reported and skipped rather than causing the entire file to fail.

Default limits:

- Backend import file limit: 100 MB
- Next.js proxy body limit: 101 MB, including multipart overhead
- Normal non-upload API body limit: 10 MB
- Upload/validation client timeout: 120 seconds

Adjust the backend and proxy limits together if requirements change.

## Full-text document indexing

ResearchHub keeps publication metadata and downloaded/indexed documents separate. A publication can exist without a local PDF, and a document can be registered before it is linked to a normalized publication.

Expected source directories under the shared data mount are:

```text
data/research-documents/aau/
data/research-documents/bdu/
data/research-documents/wku/
```

Download and indexing utilities are intentionally explicit administrative commands. Inspect help before processing a large repository:

```powershell
docker compose exec api python -m scripts.document_downloader.cli --help
docker compose exec api python scripts/index_downloaded_documents.py --help
```

After files are registered, open **Indexed documents** in the frontend. Document detail pages expose indexing status, page/chunk counts, public source links, a registered-PDF preview, and bounded full-text chunk queries. Local paths and raw vectors are not returned.

Typical document processing states are `pending`, `extracting`, `chunking`, `embedding`, `indexed`, and `failed`. Restart the worker after changing extraction, chunking, embedding, or Celery task code:

```powershell
docker compose restart worker
docker compose logs -f worker
```

Document data under `./data` is bind-mounted into the API and workers. Moving files outside that mount makes registered previews unavailable until records and paths are reconciled.

## Search and AI workflows

### Metadata search

The publication catalogue supports title text and normalized author, keyword, journal, year, and language filters.

### Semantic search

Semantic search stores normalized publication embeddings in PostgreSQL using pgvector cosine distance. Generate missing embeddings with:

```powershell
docker compose exec api python scripts/generate_publication_embeddings.py --source aau-etd
```

Model loading can be CPU- and memory-intensive. Interactive query embeddings currently use the configured embedding model; bulk generation belongs on the `ai_embeddings` Celery queue in scaled deployments.

See [docs/SEMANTIC_SEARCH.md](docs/SEMANTIC_SEARCH.md).

### AI research assistant

The assistant retrieves relevant publication metadata and abstracts, produces grounded answers, and returns supporting sources. Local deterministic providers are the safe default. Optional Ollama or OpenAI-compatible providers must be explicitly enabled through environment settings.

AI output should be treated as research assistance, not authoritative scholarly evidence. Users should verify cited publications and original documents.

See [docs/AI_RESEARCH_INTELLIGENCE.md](docs/AI_RESEARCH_INTELLIGENCE.md).

The upgraded research assistant and indexed-document UI, API routes, citation
security model, verification commands, and current staged limitations are
documented in [docs/advanced-ui-features.md](docs/advanced-ui-features.md).

#### Assistant workspace controls

The desktop assistant uses three independently managed areas:

- **Conversation history:** use the top-left menu button to show or hide saved conversations. History supports search, university/date filters, rename, pin, delete, model metadata, and activity groups.
- **Chat workspace:** expands automatically when either side panel is hidden. It includes grounded Markdown answers, abortable generation, export, print, feedback, follow-up suggestions, and a sticky keyboard-friendly composer.
- **Research context:** use the **Context** button to show or hide filters, retrieved sources, page-level evidence, and temporary attachments.

On smaller screens, history becomes a left drawer and research context becomes a right-side overlay. Both panels expose accessible expanded state and keyboard dismissal; hiding them does not discard the current conversation or filters.

### AI providers and Ollama

The default `local` provider is deterministic and extractive. It is suitable for offline development and grounding verification, but it is not equivalent to a generative language model. Provider selection is server-side; the browser never receives provider credentials.

To enable Ollama locally, use the optional Compose overlay:

```powershell
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d ollama
docker compose -f docker-compose.yml -f docker-compose.ollama.yml exec ollama ollama pull qwen2.5:7b
```

Then configure `.env` with the model you actually pulled:

```dotenv
RESEARCHHUB_AI_CHAT_PROVIDER=ollama
RESEARCHHUB_AI_CHAT_MODEL=qwen2.5:7b
RESEARCHHUB_AI_ENABLE_OLLAMA=true
RESEARCHHUB_OLLAMA_BASE_URL=http://ollama:11434
```

Restart API and AI-capable workers after changing provider settings:

```powershell
docker compose -f docker-compose.yml -f docker-compose.ollama.yml restart api worker
docker compose logs -f api worker ollama
```

Verify that the model is installed and reachable from the API network:

```powershell
docker compose -f docker-compose.yml -f docker-compose.ollama.yml exec ollama ollama list
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://ollama:11434/api/tags', timeout=10).read().decode())"
```

The Ollama image and language model are separate downloads. If Ollama is unavailable, times out, or is still starting, the assistant automatically uses the offline `grounded-local-v2` provider and records that model in the response. Remote-provider connection attempts fail fast, while the browser allows a longer bounded chat request than ordinary API calls:

```dotenv
NEXT_PUBLIC_API_TIMEOUT_MS=30000
NEXT_PUBLIC_AI_TIMEOUT_MS=210000
```

The longer chat timeout does not disable cancellation: users can still stop an active request from the composer.

Keep retrieval grounding enabled even when using a stronger model. A fluent answer without supporting records is not a verified research result.

## Application routes

| Frontend route            | Purpose                                                |
| ------------------------- | ------------------------------------------------------ |
| `/`                       | Research dashboard and managed-source health           |
| `/publications`           | Publication catalogue                                  |
| `/publications/[id]`      | Publication metadata and research-intelligence actions |
| `/search/semantic`        | Natural-language publication discovery                 |
| `/ai/assistant`           | Persistent grounded research workspace                 |
| `/documents`              | Indexed full-text document catalogue                   |
| `/documents/[documentId]` | Secure PDF preview and chunk browser                   |
| `/universities`           | Ethiopian university catalogue                         |
| `/repositories`           | Managed source catalogue                               |
| `/repositories/new`       | Source configuration and connection testing            |
| `/repositories/[id]`      | Harvest, import, edit, disable, and removal workflows  |
| `/harvest/jobs/[id]`      | Job progress, events, counters, and record failures    |

The complete interactive API contract is available through OpenAPI at <http://localhost:8111/docs>. Principal API groups are `/api/sources`, `/api/harvest`, `/api/import`, `/api/publications`, `/api/search`, `/api/documents`, `/api/ai`, `/api/dashboard`, `/api/quality`, `/api/auth`, and `/api/universities`.

## Authentication and administration

Create an initial administrator inside the API container:

```powershell
docker compose exec api python scripts/create_admin_user.py `
  --email admin@example.edu.et `
  --username admin `
  --full-name "ResearchHub Administrator" `
  --password "replace-with-a-strong-temporary-password"
```

The current bootstrap script requires `--password`; command-line arguments may be retained in shell history. Use it only for local bootstrap, rotate the password immediately, and prefer a secret-injection workflow before production deployment. Consult the script help with:

```powershell
docker compose exec api python scripts/create_admin_user.py --help
```

Production deployments must replace `RESEARCHHUB_AUTH_JWT_SECRET` with a strong secret of at least 32 random characters and must restrict CORS origins.

See [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

## Health and observability

| Endpoint                  | Meaning                                                       |
| ------------------------- | ------------------------------------------------------------- |
| `/health/live`            | Process liveness; does not depend on external services        |
| `/health/ready`           | Readiness based on required PostgreSQL and Redis dependencies |
| `/health/dependencies`    | Dependency status details                                     |
| `/health/metrics-summary` | Database-pool summary for the current API instance            |
| `/metrics`                | Prometheus-compatible metrics                                 |

Start the observability profile:

```powershell
docker compose --profile observability up -d prometheus grafana
```

Open:

- Prometheus: <http://localhost:9090>
- Prometheus targets: <http://localhost:9090/targets>
- Grafana: <http://localhost:3001>
- Development Grafana login: `admin` / `researchhub`

Example PromQL:

```promql
researchhub_api_up
researchhub_db_pool_size
researchhub_db_pool_checked_out
researchhub_db_pool_overflow
```

Change development credentials before exposing Grafana outside a trusted local environment.

## Scaling and optional profiles

### API replicas

Nginx owns host API port `8111`; API containers expose port 8111 only inside the Compose network. This permits horizontal API scaling:

```powershell
docker compose up -d --scale api=3
```

### Isolated workers

```powershell
docker compose --profile scaling up -d
docker compose --profile ai up -d
```

Queues include `harvest`, `imports`, `ai_embeddings`, `ai_generation`, `ai_analysis`, `ai_chat`, `documents`, `notifications`, and `maintenance`. Recalculate database and Redis connection budgets before increasing worker concurrency.

### PgBouncer

```powershell
docker compose --profile pgbouncer up -d pgbouncer
```

When using transaction pooling, point the application database URLs at `pgbouncer:5432`, set `RESEARCHHUB_DB_USE_PGBOUNCER=true`, and run Alembic migrations directly against PostgreSQL.

The connection-budget formula is:

```text
total_possible_connections =
  api_instances × (DB_POOL_SIZE + DB_MAX_OVERFLOW)
  + celery_processes × celery_pool_capacity
  + scheduler_connections
  + migration_connections
  + administrative_reserve
```

See [docs/architecture/database-pooling.md](docs/architecture/database-pooling.md) and [docs/operations/scaling.md](docs/operations/scaling.md).

## Configuration

All backend settings use the `RESEARCHHUB_` prefix and are typed by Pydantic Settings. Start from [.env.example](.env.example).

Important groups:

- `DATABASE_URL`, `DB_POOL_*`, and database timeout settings
- `REDIS_URL`, connection limits, socket timeouts, and cache TTL
- `HARVEST_*`, global job capacity, batch size, retry, and request timeout
- `IMPORT_*`, storage path, upload limit, and preview count
- `AUTH_*`, JWT lifecycle, failed-login limits, and recovery-token lifetime
- `AI_*`, provider selection, model names, context limits, and feature flags
- `HTTP_*`, shared outbound-client limits and timeouts
- `CELERY_*`, task time limits and prefetch behavior
- `METRICS_*` and `LOAD_TEST_MODE`

Never commit real API keys, production passwords, JWT secrets, or private repository credentials.

## Development without Docker

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[ai,test]"
uvicorn researchhub.main:app --host 0.0.0.0 --port 8111 --reload
```

Host-based settings must use `localhost` for PostgreSQL and Redis rather than Docker service names.

### Frontend

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

If PowerShell blocks `npm.ps1`, use `npm.cmd` as shown. The default Next.js rewrite targets `http://localhost:8111` outside Docker.

## Testing and quality checks

### Backend

```powershell
ruff check .
mypy backend harvester ai
pytest
alembic -c backend/alembic.ini heads
```

Using the existing API image:

```powershell
docker compose run --rm -v "${PWD}/tests:/app/tests:ro" api pytest -q tests
```

### Frontend

```powershell
Set-Location frontend
npm.cmd run lint
npm.cmd run type-check
npm.cmd test -- --run
npm.cmd run build
```

### Docker configuration

```powershell
docker compose config --quiet
docker compose --profile scaling --profile ai --profile observability --profile pgbouncer config --quiet
```

### Recommended pre-merge gate

```powershell
ruff check backend harvester ai tests
mypy backend harvester ai
pytest

Set-Location frontend
npm.cmd run format
npm.cmd run lint
npm.cmd run type-check
npm.cmd run test
npm.cmd run build
Set-Location ..

docker compose config --quiet
```

Use Python 3.13. Running the backend suite with Python 3.10 will fail on valid modern generic syntax used by the worker code.

## Load testing

The Locust workload is intentionally non-destructive by default. Use a dedicated database and enable load-test mode:

```powershell
python -m pip install -r load-tests/requirements.txt
$env:RESEARCHHUB_LOAD_TEST_MODE = "true"
locust -f load-tests/locustfile.py `
  --headless `
  --users 5 `
  --spawn-rate 1 `
  --run-time 2m `
  --host http://localhost:8111 `
  --csv load-tests/reports/smoke
```

Progress through smoke, baseline, normal, high, target, stress, spike, soak, and recovery stages only in an isolated environment. Record hardware, replicas, active users, throughput, latency percentiles, error rate, pool utilization, queue depth, and resource usage.

The current report template explicitly records **not yet measured** until real results are supplied: [docs/performance/load-test-report.md](docs/performance/load-test-report.md).

## Troubleshooting

### Frontend reports that the API is unavailable

```powershell
docker compose ps
docker compose logs api --tail=100
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8111/health/ready').read())"
```

Inside Docker, the API hostname is `api`; in a browser or host process it is `localhost`.

### Large upload fails or returns 500/413

- Confirm `RESEARCHHUB_IMPORT_MAX_FILE_SIZE_MB` allows the file.
- Keep `experimental.proxyClientMaxBodySize` in `frontend/next.config.ts` above the backend limit for multipart overhead.
- Restart the frontend after changing Next.js configuration.
- Inspect both `docker compose logs frontend` and `docker compose logs api`.

### Harvest fails after backend code changes

Restart Celery so it loads the updated code:

```powershell
docker compose restart worker
docker compose logs worker --since=30s
```

### Duplicate source slug or endpoint

Removed sources with history are archived to preserve provenance. Creating the same slug or endpoint restores the archived connector instead of discarding its history.

### Next.js dependency corruption

If `next` reports missing internal modules, remove and reinstall only frontend dependencies rather than changing application code:

```powershell
Set-Location frontend
Remove-Item -Recurse -Force node_modules
npm.cmd ci
```

### Chat answers have no full-text evidence

Check that documents and embedded chunks exist before changing the model:

```powershell
docker compose exec postgres psql -U researchhub -d researchhub -c "SELECT extraction_status, count(*) FROM research_documents GROUP BY extraction_status ORDER BY extraction_status;"
docker compose exec postgres psql -U researchhub -d researchhub -c "SELECT count(*) AS chunks, count(embedding) AS embedded FROM document_chunks;"
docker compose logs worker --tail=200
```

Metadata-only answers are expected when matching PDFs have not been registered, extracted, chunked, and embedded.

### Migration and model disagree

```powershell
docker compose exec api alembic -c backend/alembic.ini current
docker compose exec api alembic -c backend/alembic.ini heads
docker compose exec api alembic -c backend/alembic.ini upgrade head
```

Do not edit previously applied migration files to repair a deployed database. Add a new migration.

## Backup and recovery

Back up both PostgreSQL and the document/import data mount. A database-only backup cannot restore registered PDFs, while a file-only backup cannot restore provenance, sessions, jobs, or document UUIDs.

Example local database backup:

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
docker compose exec -T postgres pg_dump -U researchhub -d researchhub -Fc > backups/researchhub.dump
```

Copy `./data` using a filesystem-aware backup tool while write-heavy imports and indexing are paused. Test restoration in a separate environment before relying on the backup. Preserve `.env` values through a secret-management system, not inside the backup repository.

For failure scenarios and recovery sequencing, see [docs/operations/failure-recovery.md](docs/operations/failure-recovery.md).

## Security notes

- Development passwords and ports in Compose are not production defaults.
- Terminate TLS at a trusted reverse proxy or ingress.
- Restrict CORS and trusted proxy headers.
- Protect administrative, source-management, import, and AI-generation endpoints with appropriate roles and permissions before public exposure.
- Store secrets in a secret manager rather than `.env` in production.
- Scan uploads, enforce object-storage policies, and back up PostgreSQL and uploaded documents.
- Do not weaken Argon2 or authorization checks to improve benchmark numbers.

## Known limitations

- The platform is under active development and has not been certified for production capacity or public multi-tenant operation.
- Authentication primitives exist, but every administrative and AI workflow must be reviewed for role enforcement before public exposure.
- The browser-native PDF viewer does not yet provide application-level thumbnails, rotation, text highlighting, or full PDF.js search controls.
- Chat responses do not yet stream tokens from the local provider.
- Retrieval metadata does not yet expose a complete lexical/semantic/reranker timing and score breakdown.
- Document summaries, saved research collections, comparison workspaces, expanded indexing administration, and AI status pages remain staged.
- Repository metadata quality and PDF availability vary by institution; ResearchHub cannot infer missing authors, years, DOI values, pages, or URLs safely.
- AI-generated or extractive output is research assistance. Verify claims against the cited publication and original document.

See [docs/advanced-ui-upgrade-plan.md](docs/advanced-ui-upgrade-plan.md) for staged implementation and [docs/advanced-ui-features.md](docs/advanced-ui-features.md) for the current advanced UI boundary.

## Documentation index

- [Architecture](docs/ARCHITECTURE.md)
- [Scalability](docs/architecture/scalability.md)
- [Concurrency control](docs/architecture/concurrency-control.md)
- [Database pooling](docs/architecture/database-pooling.md)
- [Caching](docs/architecture/caching.md)
- [Background workers](docs/architecture/background-workers.md)
- [Authentication](docs/AUTHENTICATION.md)
- [Source management](docs/SOURCE_MANAGEMENT.md)
- [Harvesting](docs/HARVESTING.md)
- [Connectors](docs/CONNECTORS.md)
- [Metadata quality](docs/METADATA_QUALITY.md)
- [Semantic search](docs/SEMANTIC_SEARCH.md)
- [AI research intelligence](docs/AI_RESEARCH_INTELLIGENCE.md)
- [Advanced UI implementation plan](docs/advanced-ui-upgrade-plan.md)
- [Advanced UI features and limitations](docs/advanced-ui-features.md)
- [Observability](docs/operations/observability.md)
- [Load testing](docs/operations/load-testing.md)
- [Capacity planning](docs/operations/capacity-planning.md)
- [Scaling operations](docs/operations/scaling.md)
- [Failure recovery](docs/operations/failure-recovery.md)

## Contributing

1. Create a focused branch.
2. Preserve existing APIs unless a migration is documented.
3. Add tests for bug fixes and concurrency-sensitive changes.
4. Run backend and frontend validation.
5. Document schema, environment, operational, or user-facing workflow changes.
6. Do not commit generated datasets, secrets, model caches, build output, or local volumes.
