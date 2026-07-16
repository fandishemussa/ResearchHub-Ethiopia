# Source Management and Harvesting

ResearchHub reuses the existing `connectors` table as its single managed-source
registry. This preserves compatibility with the current OAI-PMH engine,
workers, connector configuration, and publication provenance.

Migration `0009_source_management` extends connector health and statistics,
adds detailed harvest counters/checkpoints, and creates record-level failure
and import-file tables. It is additive and does not change harvested records.

## Available APIs

- `GET|POST /api/sources`
- `GET|PUT|PATCH|DELETE /api/sources/{id}`
- `POST /api/sources/{id}/enable`
- `POST /api/sources/{id}/disable`
- `POST /api/sources/{id}/test`
- `POST /api/sources/test-configuration`
- `GET /api/sources/{id}/health`
- `GET /api/sources/{id}/statistics`
- `GET /api/sources/{id}/harvest-history`

OAI-PMH testing calls `Identify` and `ListMetadataFormats`, validates the
configured metadata prefix, records a connection-test harvest job and event,
and updates source health. API keys, passwords, tokens, authorization values,
and secrets are stripped from submitted connection configuration and are never
included in source responses.

DSpace Discovery testing requests one HAL search result, validates the response envelope, and
reports the indexed-record count. Saved Discovery sources accept either `/server/api` or the full
`/server/api/discover/search/objects` URL; ResearchHub owns `page` and `size` pagination.

## Frontend

Use **Repositories → Add source** or open `/repositories/new`. The initial
workflow supports OAI-PMH, DSpace OAI, DSpace REST Discovery, OJS OAI, XML, JSON, and CSV source types,
institution selection, endpoint configuration, pre-save connection testing,
and source creation.

## Authorization boundary

All source reads require `sources.read`. Source creation, editing, testing, enabling, disabling,
and removal require `sources.manage`; harvest actions use their dedicated harvest permissions.

## Harvest and import workflows

Saved OAI and DSpace Discovery sources support full, incremental, and dry-run jobs. Incremental jobs
default to the last successful harvest date. Only one active job is allowed per
source. Celery executes database-configured jobs on the `harvest` queue while
persisting counters, events, result summaries, and connection health. Active
jobs can be cancelled; terminal jobs can be retried or resumed.

DSpace incremental jobs compare item `lastModified` dates. Discovery does not expose deletion
tombstones, so it cannot mark every remotely deleted item without a future reconciliation pass.

XML, JSON, and CSV uploads validate extension, MIME type, size, checksum, and
syntax before using a generated server filename. XML accepts OAI-PMH response
documents. JSON accepts one record, a list, or a `records` envelope. CSV maps
standard publication columns. Each upload must be previewed and explicitly
confirmed before normalized publications are persisted.

```text
POST /api/sources/{id}/harvest/full
POST /api/sources/{id}/harvest/incremental
POST /api/sources/{id}/harvest/dry-run
GET  /api/harvest/jobs
GET  /api/harvest/jobs/{id}
POST /api/harvest/jobs/{id}/cancel
POST /api/harvest/jobs/{id}/retry
POST /api/harvest/jobs/{id}/retry-failed
POST /api/harvest/jobs/{id}/resume
GET  /api/harvest/jobs/{id}/events
GET  /api/harvest/jobs/{id}/failures
POST /api/import/{xml|json|csv}
POST /api/import/{job_id}/preview
POST /api/import/{job_id}/confirm
POST /api/import/{job_id}/cancel
```

The source detail page at `/repositories/{id}` provides health tests, harvest
actions, upload/preview/confirm, and job history. `/harvest/jobs/{id}` polls
active work and shows counters, events, failures, cancellation, and retry.
