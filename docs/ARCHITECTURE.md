# Architecture

ResearchHub Ethiopia is structured as a modular platform that can grow from a
single university deployment into national research information infrastructure.

## Clean Architecture Layers

- `domain`: stable DTOs and value objects that describe universities,
  repositories, publications, connectors, and search filters.
- `application`: use-case services for publication ingestion, catalog management,
  search, analytics, connector configuration, harvest jobs, and quality reports.
- `infrastructure`: SQLAlchemy models, database sessions, repositories, and other
  concrete adapters.
- `api`: FastAPI routers and dependency injection.
- `harvester`: source connectors, normalization, validation, deduplication, and
  connector execution independent of the web API.
- `ai`: semantic service contracts for search, enrichment, similarity, and
  recommendations.

## Database Principles

The schema is normalized for long-term reporting and metadata stewardship:

- Publications are canonical records.
- Authors and keywords are normalized and connected through join tables.
- Repositories and connectors are configured separately so a source can be
  disabled, rescheduled, or reconfigured without losing publication metadata.
- Harvest jobs and logs preserve operational history.
- Metadata history preserves field-level provenance.
- Quality reports track metadata completeness over time.

## Connector-Driven Onboarding

Adding a university should require configuration:

1. Register a university.
2. Register one or more repositories.
3. Register connectors with base URLs and source-specific JSON configuration.
4. Queue or schedule harvest jobs.

The connector contract requires every source to implement:

- `identify`
- `collect`
- `normalize`
- `validate`
- `export`

This keeps DSpace, OJS, Crossref, OpenAlex, DataCite, ORCID, and future sources
behind the same ingestion boundary.

## Search and Analytics

PostgreSQL full-text search supports title and abstract search, while normalized
tables support author, keyword, journal, year, and language filters. Analytics are
read models over the same normalized schema and can later be materialized for
large national deployments.

## AI Roadmap

The `ai` package starts with deterministic fallbacks so the platform can run in
restricted environments. Production deployments can enable sentence transformers,
pgvector, LangChain, Ollama, and OpenAI-compatible APIs for semantic search,
metadata enrichment, keyword generation, publication similarity, recommendations,
RAG, and an LLM assistant.

