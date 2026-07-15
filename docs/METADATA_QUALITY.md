# Metadata Quality Assessment

ResearchHub Ethiopia includes a metadata quality engine that evaluates harvested
and manually entered publications across six dimensions:

- completeness
- validity
- consistency
- uniqueness
- timeliness
- accessibility

The default weights are:

```json
{
  "completeness": 0.30,
  "validity": 0.20,
  "consistency": 0.15,
  "uniqueness": 0.15,
  "timeliness": 0.10,
  "accessibility": 0.10
}
```

Weights are normalized at runtime and can be overridden with the
`RESEARCHHUB_METADATA_QUALITY_WEIGHTS` environment variable as JSON.

## Scoring

Each dimension is scored from 0 to 100. The weighted final score maps to grades:

- A: 90-100
- B: 80-89
- C: 70-79
- D: 60-69
- F: below 60

Deleted source records can still be assessed, but active-publication averages
exclude deleted records unless the caller explicitly includes them.

## Persistence

Reports are stored in `quality_reports`. The table keeps history:

- the latest row for each publication has `is_current = true`
- when important fields or scores change, the previous report is preserved and a
  new current report is inserted
- unchanged recalculations reuse the current row
- `publications.quality_score` is updated with the latest final score

Run the migration:

```bash
alembic -c backend/alembic.ini upgrade head
```

## API

The Phase 1 quality endpoints are:

```text
GET  /api/quality/publications/{publication_id}
GET  /api/quality/summary
GET  /api/quality/issues
GET  /api/quality/low-quality
POST /api/quality/publications/{publication_id}/recalculate
POST /api/quality/recalculate-all
```

The legacy `GET /api/quality/reports` route remains available for simple current
report listing.

Supported filters include grade, score range, issue type, university,
repository, journal, year, and active/deleted status. URL reachability checks are
available but disabled by default:

```env
RESEARCHHUB_METADATA_QUALITY_CHECK_URL_REACHABILITY=false
RESEARCHHUB_METADATA_QUALITY_URL_TIMEOUT_SECONDS=3
```

## Local Validation

```bash
pytest tests/test_metadata_quality.py
python -m unittest tests.test_metadata_quality -v
```
