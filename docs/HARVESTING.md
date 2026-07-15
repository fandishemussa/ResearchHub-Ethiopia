# Harvesting Engine

ResearchHub Ethiopia includes a connector-driven harvesting engine that can run
one or many metadata connectors from JSON configuration.

## Configuration

Example config:

```json
{
  "max_concurrent_connectors": 3,
  "retry_failed_jobs": true,
  "job_max_attempts": 3,
  "connectors": [
    {
      "code": "haramaya-ir",
      "name": "Haramaya Institutional Repository",
      "connector_type": "oai-pmh",
      "source_type": "oai-pmh",
      "base_url": "https://repository.haramaya.edu.et/oai/request",
      "metadata_prefix": "oai_dc",
      "from_date": "2024-01-01",
      "schedule": "@daily",
      "enabled": true
    }
  ]
}
```

The repository includes a template at:

```text
harvester/config/harvest_connectors.example.json
```

## Engine Behavior

For each connector the engine:

- creates a harvest job
- executes the connector
- normalizes metadata into the canonical publication model
- validates records
- skips in-run duplicates
- sends normalized metadata to `HarvestPersistenceService`
- upserts existing database records instead of creating duplicates
- resolves or creates universities, repositories, journals, authors, keywords,
  publication types, and licenses
- stores raw metadata, normalized metadata, source URLs, repository datestamps,
  harvested timestamps, and quality scores
- records harvest logs
- updates final harvest job counters
- returns a structured harvest report

## Persistence Pipeline

`HarvestPersistenceService` uses this identity matching order:

1. DOI exact match
2. source ID plus external ID exact match
3. normalized title plus publication year plus first author
4. normalized title similarity fallback

Deleted OAI records are never physically deleted. Existing records are marked
`is_deleted=true`, raw tombstone metadata is preserved, and a `metadata_history`
entry is written for the delete transition. If a tombstone arrives before its
original record, the service stores a minimal deleted tombstone record for audit.

The persistence result reports:

- created count
- updated count
- unchanged count
- deleted count
- failed count
- duplicate count

## Running Once

From application code:

```python
from researchhub.application.scheduler import run_once

report = run_once("harvester/config/harvest_connectors.example.json")
```

## Celery Tasks

```bash
celery -A researchhub.application.worker call researchhub.harvest.run_config \
  --args='["harvester/config/harvest_connectors.example.json"]'
```

Run one connector:

```bash
celery -A researchhub.application.worker call researchhub.harvest.run_connector \
  --args='["haramaya-ir", "harvester/config/harvest_connectors.example.json"]'
```

## Scheduling

Set:

```text
RESEARCHHUB_HARVEST_CONFIG_PATH=harvester/config/harvest_connectors.example.json
```

Then start the scheduler:

```bash
python -m researchhub.application.scheduler
```

Supported schedule formats:

- `@hourly`
- `@daily`
- `interval:3600`
- `interval:minutes=30`
- `cron:*/15 * * * *`
