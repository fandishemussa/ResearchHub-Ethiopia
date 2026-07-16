# Database Schema Audit

**Audited:** 2026-07-16  
**Declared Alembic head:** `0013_chat_workspace`

## Result

The repository has exactly one declared Alembic head and a linear revision chain:

`0001_initial_schema` → `0002_storage_layer_indexes` → `0003_metadata_pipeline` →
`0004_metadata_quality_assessment` → `0005_publication_embeddings` →
`0006_research_chatbot` → `0007_research_intelligence` →
`0008_ai_operations_foundation` → `0009_source_management` →
`0010_authentication_foundation` → `0011_concurrency_indexes` →
`0012_document_chunks` → `0013_chat_workspace`.

`alembic -c backend/alembic.ini heads` returns one head. `current` and schema introspection require a
reachable PostgreSQL instance and are therefore runtime release-checklist items, not source-audit
claims.

## Model and migration coverage

| Area | Persisted model coverage | Migration coverage | Finding |
|---|---|---|---|
| Institutions | University, faculty, department | Initial schema | Aligned foundation; the requested campus, research center and research group entities do not exist |
| Catalogue | Repositories, journals, publication types, licenses, authors, organizations, publications and join entities | Initial and metadata-pipeline migrations | Strong normalized foundation |
| Harvest/import | Connectors, jobs, logs, failures, import files, metadata history | Initial, metadata-pipeline and source-management migrations | Persisted operational foundation |
| Quality | Quality reports | `0004` | Scores/issues are persisted, but no normalized stewardship/correction state machine |
| Publication vectors | Inline publication vector plus versioned publication embeddings | `0005`, `0008`, `0011` | Vector dimension is 384; HNSW cosine index is declared |
| AI intelligence | Chat, feedback, summaries, AI keywords/citations, duplicates, trends, jobs and usage | `0006`–`0008`, `0013` | Implemented foundation |
| Authentication | Users, roles, permissions, joins, refresh and recovery tokens | `0010` | Schema foundation exists; authorization enforcement is absent |
| Full text | Research documents and document chunks | `0012` | ORM drift was repaired during this audit; see below |
| Audit/stewardship | None | None | Missing; requires a forward migration |
| Researcher profiles | Basic author only | Initial schema | Enterprise profile fields/workflows are missing; requires a forward migration |

## Full-text table verification

Migration `0012_document_chunks` defines the requested `research_documents` fields: UUID primary
key, publication foreign key with `SET NULL`, source, external ID, title, managed local path,
document and landing URLs, filename, MIME type, extension, SHA-256 checksum, file size, page and
character/chunk counts, status/error, JSONB metadata, download/extract/index timestamps and audit
timestamps.

It also defines the requested `document_chunks` fields: UUID primary key, cascading document
foreign key, stable chunk index, page range, section, content, character/token counts, Vector(384),
embedding model, content hash, JSONB metadata, embedded/created timestamps, unique
`(document_id, chunk_index)`, and an HNSW `vector_cosine_ops` index.

Before this audit, the ORM omitted several columns already present in migration `0012`. The ORM now
maps those existing columns. No new migration was created because changing the database would have
been incorrect: the database migration was already the authoritative, more complete definition.

## Constraints and type observations

- PostgreSQL UUID and JSONB are used consistently in the normalized and operational models.
- Operational timestamps use `DateTime(timezone=True)` and PostgreSQL `now()` defaults where
  declared.
- Publication/source identity, publication-author, publication-keyword, embedding-version, role,
  permission and document-chunk business keys have unique constraints.
- Document chunks cascade on document deletion. User role/permission/session children cascade on
  user/role deletion. Publication deletion behavior is less consistently explicit and should be
  tested against the target schema before any retention-policy claim.
- Index names in migrations are explicit for critical vector, search, source/status and concurrency
  indexes. Several model-side unnamed unique constraints rely on database-generated names; do not
  rename them in-place on an existing deployment.

## Required runtime checks

Run these against the intended database before release:

```powershell
.\.venv\Scripts\alembic.exe -c backend/alembic.ini current
.\.venv\Scripts\alembic.exe -c backend/alembic.ini heads
.\.venv\Scripts\alembic.exe -c backend/alembic.ini check
```

Then inspect vector dimensions/index operators and compare reflected columns with
`Base.metadata`. Any repair must be a new forward migration. Never edit a migration that has
already been applied.

## Remaining schema work

The enterprise target still needs deliberately designed forward migrations for immutable audit
events, metadata correction/stewardship, expanded organizational hierarchy, researcher profiles,
and demo-record markers. These are missing capabilities, not safe candidates for speculative
columns added during a schema-alignment repair.
