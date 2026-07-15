# ResearchHub Ethiopia AI Research Intelligence

The module provides local-first, evidence-grounded research assistance without
requiring a paid model provider.

## Database migration

Apply the chatbot and research-intelligence migrations before using write APIs:

```powershell
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
```

Migrations `0006_research_chatbot` and `0007_research_intelligence` add chat
history, feedback, summaries, AI keywords, citation cache, and duplicate review
records. Migration `0008_ai_operations_foundation` adds versioned publication
embeddings with an HNSW cosine index, cached research trends, AI job progress,
usage telemetry, and richer summary provenance. These migrations do not modify
harvested publication metadata or the XML/OAI-PMH pipeline.

## Provider and text architecture

`researchhub_ai.providers` defines one provider contract for text, chat,
embeddings, health checks, and model discovery. Implementations are available
for local sentence-transformers, Ollama, and OpenAI-compatible HTTP APIs. The
factory rejects incomplete remote configurations before a request is sent.

`PublicationTextBuilder` is the canonical input builder for embeddings,
summaries, keywords, duplicate comparison, and chatbot documents. It decodes
HTML entities, removes markup, normalizes whitespace and line breaks,
deduplicates repeated values, excludes deleted records, enforces a maximum
length, and returns a deterministic SHA-256 content hash.

## API surface

- `POST /api/ai/chat/query`
- `POST|GET /api/ai/chat/sessions`
- `GET|DELETE /api/ai/chat/sessions/{id}`
- `POST /api/ai/chat/sessions/{id}/messages`
- `GET /api/ai/chat/sessions/{id}/messages`
- `POST /api/ai/chat/feedback`
- `POST /api/ai/publications/{id}/summarize`
- `GET /api/ai/publications/{id}/summary`
- `GET /api/ai/publications/{id}/summaries`
- `POST /api/ai/publications/{id}/extract-keywords`
- `GET /api/ai/publications/{id}/citation?style=apa7`
- `POST /api/ai/duplicates/publication/{id}`
- `GET /api/ai/duplicates`
- `POST /api/ai/duplicates/{id}/{confirm|reject|ignore}`
- `GET /api/ai/trends/overview`
- `GET /api/ai/publications/{id}/similar`
- `GET /api/search/semantic`

Citation styles: `apa7`, `mla9`, `chicago-author-date`, `chicago-notes`,
`harvard`, `ieee`, `vancouver`, `bibtex`, `ris`, and `csl-json`.

## Grounding and safety

The local chatbot retrieves only active publications and can restrict results
to a university through repository or journal ownership. Answers cite stored
publication IDs. Empty retrieval produces an explicit no-evidence response.
Common prompt-injection attempts requesting secrets, system prompts, shell
commands, or database credentials are rejected.

The current repository does not contain the authentication/RBAC module claimed
by the original specification. Chat actor fields are nullable for future
identity integration. Private-record retrieval and administrative merge/edit
operations must remain disabled until real authentication and authorization
dependencies are added.

## Configuration

Settings use the existing `RESEARCHHUB_` prefix:

```dotenv
RESEARCHHUB_AI_PROVIDER=local
RESEARCHHUB_AI_CHAT_MODEL=grounded-local-v1
RESEARCHHUB_AI_REQUEST_TIMEOUT=60
RESEARCHHUB_AI_MAX_RETRIES=3
RESEARCHHUB_AI_MAX_CONTEXT_PUBLICATIONS=8
RESEARCHHUB_AI_MAX_MESSAGE_CHARS=4000
RESEARCHHUB_AI_DEFAULT_TEMPERATURE=0.1
RESEARCHHUB_AI_ENABLE_OPENAI=false
RESEARCHHUB_AI_ENABLE_OLLAMA=false
RESEARCHHUB_OLLAMA_BASE_URL=http://ollama:11434
```

Secrets are never returned by an API schema.

## Known boundaries

- The chatbot currently uses safe local extractive generation, not streaming.
- Summaries use title and abstract only and explicitly identify that scope.
- Keyword extraction is English frequency-based; multilingual extractors remain future work.
- Duplicate scanning creates review candidates and never merges or deletes records.
- Trend overview reports publication frequency, not research impact or causality.
- Long-document jobs, provider fallback, usage quotas, authenticated RBAC, and audit integration require their underlying platform modules before they can be enabled safely.
