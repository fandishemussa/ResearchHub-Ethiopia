# ResearchHub Ethiopia Advanced UI Upgrade Plan

## Objective

Evolve the existing Next.js, FastAPI, PostgreSQL/pgvector, Redis, and Celery application into a cohesive research-intelligence workspace without replacing its working harvesting, indexing, semantic search, chatbot, or observability foundations.

## Existing foundations confirmed

- App Router frontend with Tailwind, React Query, Lucide icons, dark mode, and reusable `Card`, `Button`, and loading primitives.
- Grounded chatbot persistence in `chat_sessions`, `chat_messages`, and `chat_feedback`.
- Hybrid retrieval from publication metadata and 384-dimensional `document_chunks` embeddings.
- Indexed PDF records in `research_documents`, with registered local paths, public document/landing URLs, page ranges, and chunk metadata.
- Local extractive `grounded-local-v2`, optional Ollama, and OpenAI-compatible provider adapters.
- Separate Celery queues for harvesting, imports, embeddings, documents, AI generation, and analysis.
- Docker bind mounts for backend, frontend, AI, harvester, scripts, data, and Hugging Face cache; ports remain unchanged.

## Implementation stages

### 1. Research assistant workspace

- Keep the new rich Markdown, temporary attachments, modes, filters, settings, abort, export, feedback, citations, grounding, and evidence components.
- Restore persistent session discovery through the existing `/api/ai/chat/sessions` routes.
- Add backward-compatible session rename and pin support with a new Alembic migration.
- Add search, university/date filtering, grouped history, responsive drawers, and safe delete confirmation.
- Add safe retrieval diagnostics and timing/provider metadata without exposing prompts, vectors, filesystem paths, or secrets.

### 2. Indexed document experience

- Add paginated document and chunk DTOs/services/routes under the existing API version router.
- Add a secure registered-document PDF response and reject missing, non-PDF, or unavailable records.
- Build `/documents/[documentId]` with metadata, status, chunk search/filtering, copy actions, and chat deep links.
- Use the browser PDF viewer initially to preserve bundle size; enhance with PDF.js only if its cost and range behavior are justified.

### 3. Discovery and comparison

- Extend semantic search with document-chunk and combined modes, URL-synchronized filters, matched excerpts/pages, selection, export, and chat links.
- Add `/research/compare` for 2–5 explicitly selected records. Keep every generated statement tied to source citations.

### 4. Saved workspace

- Implement a clearly labeled local single-user workspace using browser storage because user authentication is not yet required across the current UI.
- Store collections, notes, tags, publication/document references, and saved answers—not credentials or raw embeddings.
- Support Markdown, bibliography, CSV, and JSON exports.

### 5. Operations and intelligence

- Add efficient aggregate services for dashboard research metrics.
- Add paginated document administration, safe reindex/retry operations, and summarized queue state.
- Add an AI status endpoint/page exposing provider/model/vector/database/Redis/worker health while excluding secrets.

### 6. Quality, security, and documentation

- Validate all pagination, filters, IDs, thresholds, and bounded list sizes server-side.
- Sanitize Markdown by rendering a restricted React element subset; never render raw HTML.
- Serve PDFs only by registered UUID and never return `local_path` to frontend DTOs.
- Preserve old citation rows that only include `publication_id`.
- Add component, API, retrieval, serialization, pagination, and document-serving security tests.
- Run Prettier, ESLint, TypeScript, Vitest, Ruff, Pytest, Next.js production build, and `docker compose config`.
- Document new routes, APIs, Ollama configuration, citations, document security, commands, and honest limitations.

## Migration strategy

- Do not edit migrations `0001`–`0012`.
- Add a new migration only for persistent session metadata required by the upgraded history UI (pin state and optional activity metadata if not derivable).
- Keep stored messages and legacy citation JSON backward compatible.

## Delivery boundaries

The work is delivered in the stages above. Each stage must remain runnable and tested before the next stage expands the public surface. Features requiring unavailable data are shown as unavailable; the UI will not fabricate metrics, scores, summaries, task state, or model timings.
