# Enterprise Prototype Implementation Audit

**Audit date:** 2026-07-16  
**Scope:** repository evidence available before enterprise-prototype changes  
**Audience:** ResearchHub maintainers and Haramaya University prototype reviewers

## Method and status rules

This audit compares claims with SQLAlchemy models, the linear Alembic history through
`0013_chat_workspace`, FastAPI routes and services, worker code, Next.js routes and components,
tests, Compose configuration, and existing operations documentation. A capability is not marked
`VERIFIED_IMPLEMENTED` merely because a model, route, or screen exists. That status requires a
coherent persisted workflow and direct automated evidence. Live integrations and production
capacity remain `REQUIRES_PRODUCTION_VALIDATION` until measured in the target environment.

Status vocabulary is intentionally limited to: `VERIFIED_IMPLEMENTED`,
`IMPLEMENTED_FOUNDATION`, `PARTIALLY_IMPLEMENTED`, `BROKEN`, `MISSING`, `PLANNED`, and
`REQUIRES_PRODUCTION_VALIDATION`.

## Executive finding

ResearchHub is a credible research-ingestion and retrieval prototype foundation, not yet a
complete enterprise research-information system. Its strongest areas are normalized publication
storage, OAI-PMH/source operations, metadata quality calculation, vector search, document
chunking, and grounded-chat foundations. Its largest gaps are centralized authorization,
tenant-scope enforcement, enterprise administration, researcher profiles, audit logging,
metadata stewardship, backup/restore tooling, and leadership dashboards.

The most urgent defect is authorization: sensitive source, harvest, import, catalogue-write,
quality-write, document, and AI routes currently do not depend on the existing authenticated-user
dependency. Role and permission tables exist, but there is no policy service and no route-level
permission enforcement. These routes must not be exposed to an untrusted network in the current
state.

## Capability matrix

| Capability | Claimed status | Backend | Frontend | Database | Tests | Actual status | Missing work | Priority |
|---|---|---|---|---|---|---|---|---|
| Managed repository sources | Implemented | Source CRUD, lifecycle, connection and harvest routes exist | List, add, detail/edit actions exist | Connectors plus source configuration in connector metadata | Source and operations tests exist | PARTIALLY_IMPLEMENTED | Authorization, archive/restore semantics, richer filters, schedule/rate-limit UI | P0 |
| OAI-PMH connection testing | Implemented | Identity/format probing exists | Test actions and result feedback exist | Results reflected in source health metadata | Parser/connector tests | PARTIALLY_IMPLEMENTED | Live endpoint matrix, sanitized structured diagnostics, latency verification | P1 |
| Full/incremental/dry-run harvest | Implemented | Modes, job APIs and worker paths exist | Actions and job-detail UI exist | Jobs, logs, failures and checkpoints persist | Harvest tests exist | PARTIALLY_IMPLEMENTED | Permission enforcement, live long-run/resumption validation, downloadable summary | P0 |
| Harvest progress, events, failure, retry, cancel | Implemented | Job lifecycle endpoints and counters exist | Progress/events/failures are displayed | Harvest jobs/logs/failures persist | Lifecycle coverage exists | PARTIALLY_IMPLEMENTED | Retry-failed-record workflow and consistent partial-completion states | P1 |
| JSON/CSV/XML metadata import | Implemented | Upload, preview, confirm and cancel routes exist | File upload is embedded in source detail | Import file/job state persists | Import tests exist | PARTIALLY_IMPLEMENTED | Dedicated import list/detail, upload progress, MIME/size UX, failure download, auth | P0 |
| Universities and organizational hierarchy | Implemented | University CRUD foundation; no hierarchy CRUD | University catalogue only | University/faculty/department exist; no campus/center/group | Limited catalogue tests | IMPLEMENTED_FOUNDATION | Full hierarchy, branding/settings, scoped CRUD, validation and UI | P1 |
| Publication catalogue and provenance | Implemented | Catalogue CRUD/search services exist | List and detail exist | Rich normalized publication graph | Service/API tests exist | PARTIALLY_IMPLEMENTED | Complete filter contract, correction history UI, write authorization | P1 |
| Researcher directory and profiles | Claimed enterprise target | Author listing only | No researcher directory/profile routes | Author has basic identity fields only | Basic author/catalogue coverage | MISSING | Profile domain, privacy, claims, verification, CV and expertise UI/API | P2 |
| Metadata quality scoring | Implemented | Six-dimension assessment/report endpoints | No dedicated quality route | Reports and issue JSON persist | Strong calculation/repository tests | IMPLEMENTED_FOUNDATION | Dashboard and stewardship state machine with before/after audit | P1 |
| Metadata correction workflow | Claimed enterprise target | No correction/approval API | Missing | No normalized corrections/workflow/audit model | Missing | MISSING | Persisted DETECTED-to-CLOSED workflow, permissions and UI | P1 |
| Publication embeddings and semantic search | Implemented | 384-dimension encoding/query services exist | Semantic-search page exists | Vector(384), HNSW cosine index | Backend and frontend search tests | PARTIALLY_IMPLEMENTED | Reproducible relevance evaluation, admin debug, live corpus validation | P1 |
| Hybrid and full-text chunk search | Implemented | Chunk retrieval/vector foundations exist; full hybrid contract is incomplete | No unified hybrid-search experience | Chunk vectors and text persist | Document/chat retrieval tests | IMPLEMENTED_FOUNDATION | Lexical+vector fusion endpoint/UI, score explanation and evaluation dataset | P1 |
| PDF registration/extraction/chunking/indexing | Implemented | Services and scripts exist | Document list/detail/chunks/preview exist | Research documents and chunks persist | Document tests exist but full suite collection currently breaks | BROKEN | Align document ORM with migration, restore missing downloader helper, admin retry actions | P0 |
| Secure document access | Implemented | ID-based content/view endpoints validate managed paths | Preview links exist | Local paths persist internally | Path/document tests exist | PARTIALLY_IMPLEMENTED | Authentication, document permission/scope and restricted/embargo enforcement | P0 |
| Grounded AI research assistant | Implemented | Retrieval, citations, sessions, feedback and provider fallback exist | Advanced chat, drawers, citations and export exist | Sessions/messages/feedback persist | Chat/context tests exist | PARTIALLY_IMPLEMENTED | Route authorization, restricted-data policy, live Ollama model validation | P0 |
| Summaries, keywords, citations, trends, duplicates | Implemented | Endpoints/services and persistence exist | Publication details expose only part of this set | Dedicated AI tables exist | Research-intelligence tests exist | IMPLEMENTED_FOUNDATION | Complete UI workflows, job UX, permissions and corpus-level validation | P1 |
| Authentication/session security | Foundation | Argon2, JWT, refresh rotation, revocation, lockout, reset/verify foundations | No login/session application UI | Users, roles, permissions, sessions/tokens exist | Auth tests exist | IMPLEMENTED_FOUNDATION | Browser session design, login UI, audit events, secure deployment validation | P0 |
| Role-based authorization | Claimed enterprise target | Only `require_authenticated_user`; no policy dependency | No permission-aware navigation/admin | Role/permission join tables exist | No route permission matrix tests | BROKEN | Central permission constants/service, seeding, scope enforcement, admin UI | P0 |
| University/department tenant scope | Claimed enterprise target | Scope IDs exist on users, but route/service enforcement is absent | Missing | Relevant foreign keys exist | Missing negative-scope tests | BROKEN | Central scope dependencies plus query/write filtering and IDOR tests | P0 |
| Executive research dashboard | Claimed enterprise target | Basic aggregate dashboard endpoints | Basic platform dashboard | Derivable catalogue data | Limited analytics tests | IMPLEMENTED_FOUNDATION | Role-aware drill-down, institutional filters, exports and freshness | P2 |
| Enterprise administration area | Claimed enterprise target | No admin router for users/roles/settings/health | Missing | Some auth foundations | Missing | MISSING | Coherent `/admin` API/UI with permission-aware navigation | P2 |
| Audit logging | Claimed enterprise target | No general audit service/middleware | Missing | No audit-event table | Missing | MISSING | Safe immutable event model, hooks, filters/export UI | P0 |
| Health, metrics and observability | Implemented | Liveness/readiness/Prometheus foundations exist | No operations dashboard | Not applicable | Health/metrics coverage exists | PARTIALLY_IMPLEMENTED | Worker/queue/model/storage dependency detail, alerts and UI | P1 |
| Grafana/Prometheus deployment | Implemented | Metrics endpoint and scrape/provisioning files exist | Grafana is external | Time-series external to app DB | Config-level evidence | REQUIRES_PRODUCTION_VALIDATION | Start stack, verify targets/dashboards and alert rules | P2 |
| Backup and recovery | Claimed enterprise target | No safe first-party scripts found | Missing status UI | PostgreSQL/documents can be backed up externally | Missing | MISSING | Dump, verify, guarded restore, document backup and tested runbook | P1 |
| Docker deployment | Implemented | Compose/API/worker/infra definitions exist | Frontend container and Nginx routes exist | PostgreSQL/pgvector initialization exists | Compose config is testable | REQUIRES_PRODUCTION_VALIDATION | Full build/up/health verification on target host; Ollama model pull completion | P1 |
| Performance/load capacity | Foundation | Load-test foundations/metrics exist | Not applicable | Indexes/pooling foundations | No current measured run | REQUIRES_PRODUCTION_VALIDATION | Reproducible profile and measured P50/P95/P99/error/resource results | P2 |
| Enterprise demo seed/showcase | Claimed enterprise target | Existing seeds/import scripts are fragmented | No explicit showcase mode | Existing real/imported data must be preserved | Missing verifier | MISSING | Idempotent marked demo seed, verifier, claims checker and presenter script | P1 |

## Verified architectural evidence

- Alembic revisions form one declared chain from `0001_initial_schema` to
  `0013_chat_workspace`; the head still requires an Alembic command and live database check.
- Publication and document chunk embeddings are declared as 384-dimensional vectors with HNSW
  cosine indexes in migrations.
- Authentication includes password hashing, access tokens, refresh-session persistence, rotation,
  revocation, failed-attempt lockout, password-reset tokens, email-verification tokens, and Redis
  fail-closed rate limiting.
- The frontend has real routes for the platform dashboard, universities, repositories, harvest
  job detail, publications, semantic search, documents, and the research assistant.
- There are no frontend routes for login, researchers, metadata stewardship, enterprise admin,
  audit logs, operations, or executive role-specific views.

## Confirmed defects and inconsistencies

1. **Sensitive routes are unauthenticated.** Outside the authentication router, route modules use
   service dependencies but not `require_authenticated_user` or any permission dependency.
2. **Role tables are inert.** Roles and permissions are persisted but not related through ORM
   convenience relationships, seeded as the required enterprise matrix, or enforced.
3. **Document ORM/migration drift.** Migration `0012_document_chunks` defines `external_id`,
   `filename`, `file_extension`, `character_count`, `chunk_count`, `downloaded_at`, `indexed_at`,
   timestamps, chunk `token_count`, `content_hash`, `chunk_metadata`, `embedded_at`, and timestamp
   fields that are absent from the current ORM classes. This makes schema-driven operations and
   audit claims unsafe until aligned.
4. **Full test collection is broken.** `tests/test_documents.py` imports `rewrite_bdu_url`, which is
   absent from `scripts/document_downloader/bdu_handler.py`.
5. **Frontend auth is absent.** The browser has no login/session route or protected navigation,
   despite backend authentication foundations.
6. **Enterprise entities are absent.** Campus, research center, research group, researcher profile,
   correction workflow, audit event, and backup status have no complete persisted domain.

## Code-health observations

- Connector documentation intentionally identifies unimplemented provider-specific connectors;
  those must remain disabled and must not be presented as live integrations.
- Existing imported records, PDFs, migrations, and user data must be preserved. New schema repairs
  must use forward migrations.
- `frontend/tsconfig.tsbuildinfo` is a generated artifact present in the tree and should not be used
  as implementation evidence.
- Existing Ollama/context-management changes are active work and are not superseded by this audit.

## Implementation order

1. P0: repair test collection and document model drift; introduce centralized authorization and
   protect sensitive routes without breaking intentional public-read routes.
2. P0: add negative authorization/scope tests and document-access enforcement.
3. P1: add audit events and metadata stewardship foundations, then the missing high-value UI.
4. P1: add safe backup tools, demo seed/verifier/claims checker, and operational documentation.
5. P2: add researcher and executive/admin surfaces incrementally, clearly labeling foundations.
6. Validate all builds and tests locally; run Docker only when authorized and when the Ollama image
   and model are available. Capacity and production-readiness remain unclaimed.

## Audit limitations

This is a source-and-test audit. It does not assert that external university repositories are
reachable, that the local PostgreSQL schema is currently at head, that Ollama has a complete model,
or that Compose services are healthy. Those items require runtime validation and remain explicitly
classified above.
