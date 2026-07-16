# Semantic search

The canonical publication embedding service builds text from normalized research metadata, verifies 384 dimensions, stores both the compatibility vector on `publications` and the versioned record in `publication_embeddings`, and records content hashes/failures. New harvests, confirmed imports, manual creates, semantic updates, detail-page similarity requests, scheduled maintenance, the CLI, and bounded admin actions can enqueue generation.

Similarity uses cosine distance with the `vector_cosine_ops` HNSW index, excludes the current/deleted record, applies filters and minimum score, and returns explanations. A missing target vector returns `embedding_required` and queues it; it is not an HTTP 409.

Semantic query ranking is transparent hybrid scoring:

`combined = semantic_weight × semantic + lexical_weight × lexical + keyword_weight × keyword`

Weights are typed settings and must total 1. Query-encoder or empty-vector failures use lexical fallback with a warning. Relevance remains `NOT_MEASURED` until the judgment fixture is curated and the backfill completes.
