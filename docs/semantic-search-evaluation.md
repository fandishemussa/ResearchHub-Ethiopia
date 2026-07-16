# Semantic-search evaluation

Current result: **NOT_MEASURED**.

The evaluation fixture contains eight representative queries and cautious title patterns, but it does not yet contain human-verified publication identifiers. HTTP success and plausible-looking rows are not relevance measurements.

After publication embeddings are backfilled, reviewers should add verified identifiers to `tests/fixtures/semantic_search_queries.json`, run each query against a fixed database snapshot, and record:

- Recall@5 and Recall@10
- Precision@5
- Mean Reciprocal Rank
- no-result rate
- average vector-search latency

Version the database snapshot, embedding model, weights, minimum score, application commit, and timestamp with every result. Raw vectors and document text must not be included in reports.
