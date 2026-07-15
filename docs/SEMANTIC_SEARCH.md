# Publication embeddings and semantic search

ResearchHub builds semantic representations through this pipeline:

`publication metadata → deterministic text builder → SentenceTransformer →`
`normalized 384-dimensional vector → PostgreSQL/pgvector → cosine search`

The default model is `sentence-transformers/all-MiniLM-L6-v2` on CPU. Input is
formatted from title, abstract, and subjects. SentenceTransformer applies its
configured tokenizer maximum length; ResearchHub does not silently pre-truncate
metadata. Vectors are stored in `publications.embedding` and never returned by
the API.

## Local setup and validation

```powershell
python -m pip install -e ".[ai,test]"
pytest -q tests/test_semantic_embeddings.py
ruff check backend ai scripts tests
mypy backend ai scripts
```

## Docker workflow

Build only after local validation, then start infrastructure and migrate:

```powershell
docker compose build api worker
docker compose up -d postgres redis
docker compose run --rm api `
  alembic -c backend/alembic.ini upgrade head
docker compose up -d --force-recreate api worker
```

The named `huggingface-cache` volume is shared by API and worker. The first
model use downloads weights; subsequent runs reuse them. Model weights are not
downloaded during image build.

Test ten records before starting a full run:

```powershell
docker compose run --rm api `
  python /app/scripts/generate_publication_embeddings.py `
  --source aau-etd `
  --limit 10 `
  --batch-size 8 `
  --database-batch-size 10
```

Run 100 records by changing `--limit 10` to `--limit 100`. Run all candidates:

```powershell
docker compose run --rm api `
  python /app/scripts/generate_publication_embeddings.py `
  --source aau-etd `
  --batch-size 32 `
  --database-batch-size 300
```

Each database page commits independently. An interrupted run resumes because
the default candidate query selects only rows whose embedding is null. Use
`--force` only to intentionally regenerate and overwrite existing embeddings.

CPU throughput depends on abstract length and host resources. Start with batch
size 8 or 16 under memory pressure; 32 is the normal default. Monitor with
`docker stats`.

## Verification

```sql
SELECT source, embedding_model, count(*)
FROM publications
WHERE embedding IS NOT NULL
GROUP BY source, embedding_model;
```

```powershell
Invoke-RestMethod `
  "http://localhost:8111/api/search/semantic?q=public+health&limit=10&source=aau-etd"
```

## Publication similarity

Publication detail pages request explainable nearest neighbors from:

```text
GET /api/ai/publications/{publication_id}/similar
```

Supported query parameters are `limit`, `minimum_score`, `university_id`,
`year_from`, `year_to`, and `publication_type`. Results include the cosine
similarity score plus shared normalized keywords and subject topics. Raw
vectors are never returned. The endpoint returns `409` when the selected
publication has not been embedded; the frontend shows a non-blocking
availability message in that case.

## Troubleshooting

- **Model download failure:** verify internet access for the first run and that
  the `huggingface-cache` volume is writable.
- **Dimension mismatch:** use a model producing exactly 384 dimensions.
- **Missing vector extension:** apply migration `0005_publication_embeddings`
  with the pgvector PostgreSQL image.
- **Migration failure:** confirm the database user may create extensions and
  inspect `alembic current` before retrying; do not reset the data volume.
- **Memory pressure:** reduce `--batch-size` and `--database-batch-size`.
- **Interrupted run:** rerun the same command without `--force`.
- **No results:** verify embeddings exist, the source filter is correct, and
  `min_similarity` is not too restrictive.
