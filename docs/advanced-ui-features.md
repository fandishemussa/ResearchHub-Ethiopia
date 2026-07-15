# Advanced Research UI Features

This document describes the advanced UI foundation currently implemented in ResearchHub Ethiopia and the staged work that remains. It deliberately does not claim unavailable metrics or workflows.

## Implemented routes

| Route | Capability |
|---|---|
| `/ai/assistant` | Persistent research conversations, grounded answers, filters, evidence inspection, feedback, export, print, and document/publication scoping |
| `/documents` | Paginated indexed-document catalogue with source/status/title filters |
| `/documents/[documentId]` | Registered PDF preview, metadata, paginated chunks, page/section/content-type filtering, copying, and chat deep links |
| `/search/semantic` | Existing publication semantic search |

The assistant uses a three-column desktop workspace. Conversation history becomes a drawer on smaller screens, while research context and evidence become a responsive side panel. History supports search, date and university filters, pinning, renaming, deletion, model display, and activity grouping.

## Backend endpoints

The new and upgraded surfaces use the existing versioned API conventions:

- `GET /api/ai/chat/sessions`
- `GET|PATCH|DELETE /api/ai/chat/sessions/{id}`
- `GET /api/ai/chat/sessions/{id}/messages`
- `POST /api/ai/chat/query`
- `POST /api/ai/chat/feedback`
- `GET /api/documents`
- `GET /api/documents/{id}`
- `GET /api/documents/{id}/chunks`
- `GET /api/documents/{id}/content`

Pagination and filter bounds are validated by FastAPI. Embeddings and filesystem paths are never serialized by document DTOs.

## Chat and citations

The assistant sends a bounded retrieval configuration and optional repository, university, year, language, document-type, document, publication, and pinned-chunk scopes. Requests are abortable, so stale responses cannot replace a newer request. Conversation preferences are stored in browser storage; conversations and messages are stored in PostgreSQL.

Answers use a restricted React Markdown renderer. Raw HTML is not rendered. Citations tolerate legacy publication-only data and may additionally include document/chunk IDs, pages, repository, university, relevance, safe URLs, and excerpts. Missing values are shown as unavailable and are never fabricated.

Citation document links resolve by registered document UUID. The API accepts only an existing `research_documents` record whose resolved file is an existing PDF. It does not accept a path from the browser. External links are limited to HTTP(S) and open with `noopener noreferrer`.

## Document viewing

The current viewer uses the browser's native PDF support to avoid adding a heavy PDF dependency. It supports initial page deep links but does not yet provide thumbnails, rotation, text highlighting, or application-level PDF search. Chunk search is server-paginated and accepts page, section, and content-type filters.

## Configuration

Relevant environment values remain documented in `.env.example`. In Docker, browser requests use the same-origin `/backend-api` proxy; only the Next.js server uses `INTERNAL_API_URL=http://api:8111`. Do not expose the Docker hostname `api` to browser code.

For Ollama, apply the optional Compose overlay and set the provider/model variables described in `.env.example`:

```powershell
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d ollama
docker compose -f docker-compose.yml -f docker-compose.ollama.yml restart api
```

No API key, provider prompt, raw embedding, database credential, or internal exception should be returned to the frontend.

## Local verification

```powershell
cd frontend
npm run format
npm run lint
npm run type-check
npm run test
npm run build

cd ..
ruff check backend harvester ai tests
pytest
docker compose config --quiet
```

Use Python 3.13 and install the project development dependencies before running Ruff and pytest.

## Known limitations and staged work

The following requested areas are not complete yet:

- true token streaming and backend regeneration endpoints;
- provider/retrieval/generation timing breakdown and citation coverage telemetry;
- lexical, semantic, reranker, and quality diagnostics for every retrieved chunk;
- full PDF.js controls and citation text highlighting;
- document summaries and Celery summary-generation status;
- document-chunk/combined semantic-search modes and saved searches;
- comparison and saved-workspace routes;
- expanded dashboard research metrics;
- ingestion administration and AI system-status pages;
- end-to-end browser smoke coverage.

These remain staged in `docs/advanced-ui-upgrade-plan.md`. The UI must continue to display unavailable fields honestly until backend data exists.
