# Search Evaluation

## Status

Implementation and unit-test foundations exist; representative-corpus relevance is
**NOT_MEASURED**. Publication and chunk embeddings use the configured sentence-transformer and
384-dimensional vectors. HNSW indexes use cosine operators. These facts do not establish search
quality.

## Reproducible protocol

1. Select a versioned corpus snapshot and record publication/document/chunk counts.
2. Freeze embedding model name/version, dimension, lexical/vector weights, minimum score and Top K.
3. Have at least two domain reviewers create queries without seeing ranked results.
4. Label relevant publications/chunks and page evidence on a 0–3 scale.
5. Run lexical, publication-semantic, chunk-semantic and hybrid variants separately.
6. Report Recall@5/10, Precision@5/10, MRR, nDCG@10, no-result rate and P50/P95 latency.
7. Review failure classes: vocabulary mismatch, metadata gaps, OCR/extraction failure, duplicate
   dominance, tenant-filter leakage and unsafe links.
8. Store the query set and raw results without copyrighted full text or personal/sensitive data.

## Initial query themes

Use the versioned evaluation dataset in `data/search_evaluation_queries.json`. Entries are neutral
themes rather than assertions that matching Haramaya research exists. Reviewers must add relevance
labels only after loading an approved corpus.

## Acceptance

No threshold is predeclared. Stakeholders must agree per-workflow targets after the first baseline.
Search-debug scores may be exposed only to administrators; raw embeddings, restricted snippets and
filesystem paths must never be returned.

## Result template

| Variant | Corpus | Queries | Recall@10 | nDCG@10 | MRR | P95 | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Lexical | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
| Publication semantic | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
| Chunk semantic | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
| Hybrid | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | Pending |
