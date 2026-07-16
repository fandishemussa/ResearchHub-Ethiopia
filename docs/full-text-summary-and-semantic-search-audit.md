# Full-text summary and semantic-search audit

Audit date: 2026-07-16. Status is based on code inspection, database checks, and the validation recorded below.

| Area | Current behavior | Root cause | Status | Required fix |
|---|---|---|---|---|
| Summary action | Previously used publication abstract/metadata only | The intelligence service never queried `research_documents` or `document_chunks` | BROKEN | Resolve a linked document first and summarize ordered indexed chunks |
| Summary source label | Always displayed “Abstract-based summary” | Frontend hard-coded the label | BROKEN | Render the API `summary_source` and warnings |
| Downloaded-document linking | 33 indexed documents and 2,727 chunks existed, but zero documents had `publication_id` | Downloader/indexer did not persist the publication relationship | MISCONFIGURED | Central resolver, indexer `publication_id`, and repair command |
| Reachable document processing | Publication detail did not probe, register, download, or queue indexing | No shared resolution/probe workflow | MISSING | Safe probe plus bounded document download/index task |
| Publication embeddings | Zero of 40,078 publications had a compatibility vector or versioned embedding | Generator was manual, source-specific, and had no persistence triggers | BROKEN | Central idempotent service, queue triggers, bounded backfill and admin controls |
| Similar research | Missing target embedding produced HTTP 409 and a permanent empty UI | Endpoint did not enqueue generation; UI did not poll | BROKEN | Return `embedding_required`, enqueue, and poll |
| Vector dimensions | Publication and chunk vectors use 384 dimensions | MiniLM configuration and pgvector columns agree | WORKING | Retain runtime dimension guard |
| Cosine index/query | HNSW uses `vector_cosine_ops`; queries use cosine distance | Compatible operator and index class | WORKING | Preserve and test current-record exclusion/minimum score |
| Semantic ranking | Previously vector-only and returned no rows when vectors were absent | No lexical fallback or transparent hybrid scoring | PARTIAL | Configured semantic/lexical/keyword hybrid plus fallback; evaluate after backfill |
| Search relevance metrics | No verified relevance judgments exist | Production-like judgments were not curated | REQUIRES_DATA | Populate fixture identifiers and run evaluator; do not infer relevance from HTTP 200 |
| Existing indexed documents | Chunk embeddings exist but publication links need repair | Historical data predates canonical linking | REQUIRES_REINDEXING | Run the link repair, then summary/embedding backfill commands |

## Verified database evidence before repair

- Publications: 40,078
- `publications.embedding`: 0
- `publication_embeddings`: 0
- Indexed research documents: 33
- Document chunks: 2,727; embedded chunks: 2,727
- Research documents linked by `publication_id`: 0

These counts explain both symptoms in the publication-detail screenshots. They must be rechecked after migration and backfill.

## Implemented decision flow

1. Use ordered chunks from an indexed document linked to the publication.
2. Queue indexing for a registered local PDF.
3. Safely probe and queue a direct PDF download.
4. Inspect a bounded same-host repository landing page for known PDF/bitstream links.
5. Fall back to the abstract with an explicit warning.
6. Fall back to metadata and identify it as metadata-based.

The source probe accepts only HTTP(S), resolves DNS before requests, blocks non-global addresses unless explicitly trusted, limits redirects/timeouts/size, and verifies `%PDF-` bytes. It never performs unrestricted crawling.

## Remaining evidence requirements

Search quality remains `NOT_MEASURED` until verified judgments are added to `tests/fixtures/semantic_search_queries.json` and the embedding backfill completes. OCR-only, restricted, and embargoed PDFs remain explicit non-indexed states rather than being treated as full text.
