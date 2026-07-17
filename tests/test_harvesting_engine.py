"""Tests for the concurrent harvesting engine."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harvester"))

from researchhub_harvester.config import (  # noqa: E402
    HarvestConnectorDefinition,
    load_harvest_config,
)
from researchhub_harvester.connectors.base import (  # noqa: E402
    ConnectorConfig,
    MetadataConnector,
    NormalizedPublication,
    RawRecord,
    ValidationResult,
)
from researchhub_harvester.services.engine import (  # noqa: E402
    HarvestEngine,
    HarvestReport,
    aggregate_reports,
)
from researchhub_harvester.services.scheduler import build_trigger  # noqa: E402


def publication(
    identifier: str, doi: str | None = None, title: str = "Soil research"
) -> NormalizedPublication:
    """Create a normalized publication for engine tests."""

    now = datetime.now(UTC)
    return NormalizedPublication(
        external_id=identifier,
        title=title,
        abstract="Abstract",
        authors=["Tesfaye Lemma"],
        affiliations=[],
        journal="Journal",
        publisher="Publisher",
        publication_date=None,
        publication_year=2025,
        keywords=["soil"],
        subjects=["soil"],
        language="en",
        doi=doi,
        orcid=None,
        issn=None,
        isbn=None,
        license=None,
        article_url=None,
        pdf_url=None,
        repository="Repository",
        repository_identifier=identifier,
        source="test-source",
        source_type="oai-pmh",
        harvested_at=now,
        updated_at=now,
        quality_score=90.0,
        is_deleted=False,
        raw_record={"metadata_quality": {"missing_fields": [], "warnings": []}},
    )


class FakeConnector(MetadataConnector):
    """Connector fake that emits configured normalized publications."""

    def __init__(
        self,
        config: ConnectorConfig,
        publications: list[NormalizedPublication],
        *,
        fail: bool = False,
    ) -> None:
        super().__init__(config)
        self.publications = publications
        self.fail = fail
        self.closed = False

    async def identify(self) -> dict[str, Any]:
        """Return fake identity data."""

        return {"repositoryName": self.config.name}

    async def collect(self, **kwargs: Any):
        """Yield raw records or fail on demand."""

        if self.fail:
            raise RuntimeError("temporary provider failure")
        for item in self.publications:
            yield RawRecord(
                identifier=item.external_id or item.title,
                datestamp=item.updated_at,
                deleted=item.is_deleted,
                metadata={},
                header={},
                source=item.source,
                metadata_prefix=self.config.metadata_prefix,
            )

    def normalize(self, raw_record: RawRecord) -> NormalizedPublication:
        """Return the matching normalized publication."""

        for item in self.publications:
            if item.external_id == raw_record.identifier:
                return item
        return publication(raw_record.identifier)

    def validate(self, publication: NormalizedPublication) -> ValidationResult:
        """Validate fake publications."""

        return ValidationResult(valid=bool(publication.title), issues=[])

    def export(self, publications):
        """Export fake publications."""

        return [item.asdict() for item in publications]

    async def aclose(self) -> None:
        """Mark connector closed."""

        self.closed = True


class InMemoryHarvestStore:
    """In-memory store fake for engine tests."""

    def __init__(self) -> None:
        self.jobs: list[tuple[str, int]] = []
        self.logs: list[dict[str, Any]] = []
        self.publications: dict[str, NormalizedPublication] = {}
        self.finished_reports: list[HarvestReport] = []
        self.exists_calls = 0

    async def start_job(self, definition: HarvestConnectorDefinition, attempt: int) -> str:
        """Record a job start."""

        job_id = f"{definition.code}:{attempt}"
        self.jobs.append((definition.code, attempt))
        return job_id

    async def log(
        self,
        job_id: str,
        *,
        level: str,
        event: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a structured log."""

        self.logs.append(
            {
                "job_id": job_id,
                "level": level,
                "event": event,
                "message": message,
                "context": context,
            }
        )

    async def publication_exists(self, publication: NormalizedPublication) -> bool:
        """Return whether a publication is already stored."""

        self.exists_calls += 1
        return self._key(publication) in self.publications

    async def store_publication(self, publication: NormalizedPublication) -> str:
        """Insert or update a publication in memory."""

        key = self._key(publication)
        if publication.is_deleted:
            self.publications[key] = publication
            return "deleted"
        if key in self.publications:
            self.publications[key] = publication
            return "updated"
        self.publications[key] = publication
        return "inserted"

    async def finish_job(self, job_id: str, report: HarvestReport) -> None:
        """Record a finished report."""

        self.finished_reports.append(report)

    def _key(self, item: NormalizedPublication) -> str:
        """Return storage key."""

        return item.doi or f"{item.source}:{item.external_id}"


class HarvestingEngineTests(unittest.TestCase):
    """Verify harvesting engine behavior."""

    def test_load_connector_configuration_from_json_dict(self) -> None:
        """JSON config values become engine and connector definitions."""

        config = load_harvest_config(
            {
                "max_concurrent_connectors": 2,
                "job_max_attempts": 4,
                "connectors": [
                    {
                        "code": "haramaya-ir",
                        "name": "Haramaya IR",
                        "connector_type": "oai-pmh",
                        "source_type": "oai-pmh",
                        "base_url": "https://repo.example.edu/oai",
                        "from_date": "2025-01-01",
                        "schedule": "@daily",
                    }
                ],
            }
        )

        self.assertEqual(config.max_concurrent_connectors, 2)
        self.assertEqual(config.job_max_attempts, 4)
        self.assertEqual(config.connectors[0].from_date.isoformat(), "2025-01-01")
        self.assertEqual(
            config.connectors[0].to_connector_config().base_url, "https://repo.example.edu/oai"
        )

    def test_run_connector_stores_publications_and_skips_in_run_duplicates(self) -> None:
        """A connector run stores one copy of duplicate DOI records."""

        store = InMemoryHarvestStore()
        config = load_harvest_config(
            {
                "connectors": [
                    {
                        "code": "c1",
                        "name": "Connector 1",
                        "connector_type": "fake",
                        "source_type": "oai-pmh",
                        "base_url": "https://example.edu/oai",
                    }
                ]
            }
        )

        def factory(
            connector_type: str, definition: HarvestConnectorDefinition
        ) -> MetadataConnector:
            return FakeConnector(
                definition.to_connector_config(),
                [
                    publication("one", "10.1234/dup"),
                    publication("two", "10.1234/dup"),
                ],
            )

        report = asyncio.run(
            HarvestEngine(config, store, connector_factory=factory).run_connector("c1")
        )

        self.assertEqual(report.status, "succeeded")
        self.assertEqual(report.records_seen, 2)
        self.assertEqual(report.records_imported, 1)
        self.assertEqual(report.duplicates, 1)
        self.assertEqual(len(store.publications), 1)
        self.assertEqual(store.exists_calls, 1)

    def test_failed_connector_is_retried(self) -> None:
        """Failed connector attempts are logged and retried."""

        store = InMemoryHarvestStore()
        config = load_harvest_config(
            {
                "job_max_attempts": 2,
                "retry_failed_jobs": True,
                "connectors": [
                    {
                        "code": "retry-me",
                        "name": "Retry Connector",
                        "connector_type": "fake",
                        "source_type": "oai-pmh",
                        "base_url": "https://example.edu/oai",
                    }
                ],
            }
        )
        calls = {"count": 0}

        def factory(
            connector_type: str, definition: HarvestConnectorDefinition
        ) -> MetadataConnector:
            calls["count"] += 1
            return FakeConnector(
                definition.to_connector_config(),
                [publication("ok", "10.1234/ok")],
                fail=calls["count"] == 1,
            )

        report = asyncio.run(
            HarvestEngine(config, store, connector_factory=factory).run_connector("retry-me")
        )

        self.assertEqual(report.status, "succeeded")
        self.assertEqual(report.attempts, 2)
        self.assertEqual(calls["count"], 2)
        self.assertIn("harvest_retry_scheduled", {log["event"] for log in store.logs})

    def test_run_all_executes_multiple_connectors_and_aggregates_reports(self) -> None:
        """The engine runs all enabled connectors and produces a combined report."""

        store = InMemoryHarvestStore()
        config = load_harvest_config(
            {
                "max_concurrent_connectors": 2,
                "connectors": [
                    {
                        "code": "a",
                        "name": "A",
                        "connector_type": "fake",
                        "source_type": "oai-pmh",
                        "base_url": "https://a.example/oai",
                    },
                    {
                        "code": "b",
                        "name": "B",
                        "connector_type": "fake",
                        "source_type": "oai-pmh",
                        "base_url": "https://b.example/oai",
                    },
                ],
            }
        )

        def factory(
            connector_type: str, definition: HarvestConnectorDefinition
        ) -> MetadataConnector:
            return FakeConnector(
                definition.to_connector_config(),
                [publication(f"{definition.code}-1", f"10.1234/{definition.code}")],
            )

        reports = asyncio.run(HarvestEngine(config, store, connector_factory=factory).run_all())
        aggregate = aggregate_reports(reports)

        self.assertEqual(len(reports), 2)
        self.assertEqual(aggregate["succeeded"], 2)
        self.assertEqual(aggregate["records_imported"], 2)

    def test_scheduler_trigger_parsing(self) -> None:
        """Supported schedule strings compile to APScheduler triggers."""

        self.assertEqual(build_trigger("@daily").__class__.__name__, "CronTrigger")
        self.assertEqual(build_trigger("interval:60").__class__.__name__, "IntervalTrigger")
        self.assertEqual(build_trigger("interval:minutes=15").__class__.__name__, "IntervalTrigger")
        self.assertEqual(build_trigger("cron:*/10 * * * *").__class__.__name__, "CronTrigger")
        with self.assertRaises(ValueError):
            build_trigger("sometimes")


if __name__ == "__main__":
    unittest.main()
