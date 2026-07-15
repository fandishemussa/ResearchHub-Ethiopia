"""Concurrent harvesting engine with retries, reporting, and persistence hooks."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from researchhub_harvester.config import HarvestConnectorDefinition, HarvestEngineConfig
from researchhub_harvester.connectors.base import (
    MetadataConnector,
    NormalizedPublication,
    ValidationIssue,
)
from researchhub_harvester.connectors.registry import create_connector
from researchhub_harvester.services.deduplication import PublicationDeduplicator

StoreResult = Literal["inserted", "updated", "deleted", "duplicate"]
ConnectorFactory = Callable[[str, HarvestConnectorDefinition], MetadataConnector]


class HarvestStore(Protocol):
    """Persistence port used by the harvesting engine."""

    async def start_job(self, definition: HarvestConnectorDefinition, attempt: int) -> Any:
        """Create or mark a harvest job as running and return a job identifier."""

    async def log(
        self,
        job_id: Any,
        *,
        level: str,
        event: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Persist a structured harvest log event."""

    async def publication_exists(self, publication: NormalizedPublication) -> bool:
        """Return True when the normalized publication already exists."""

    async def store_publication(self, publication: NormalizedPublication) -> StoreResult:
        """Persist or update a normalized publication."""

    async def finish_job(self, job_id: Any, report: HarvestReport) -> None:
        """Persist final job status and report summary."""


@dataclass(slots=True)
class NullHarvestStore:
    """No-op store useful for dry runs and isolated unit tests."""

    async def start_job(self, definition: HarvestConnectorDefinition, attempt: int) -> str:
        """Return a synthetic job id."""

        return f"{definition.code}:{attempt}"

    async def log(
        self,
        job_id: Any,
        *,
        level: str,
        event: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Ignore log events."""

    async def publication_exists(self, publication: NormalizedPublication) -> bool:
        """Assume publications do not already exist."""

        return False

    async def store_publication(self, publication: NormalizedPublication) -> StoreResult:
        """Pretend a publication was inserted."""

        return "deleted" if publication.is_deleted else "inserted"

    async def finish_job(self, job_id: Any, report: HarvestReport) -> None:
        """Ignore final reports."""


@dataclass(slots=True)
class HarvestReport:
    """Summary report for one connector harvest execution."""

    connector_code: str
    job_id: Any
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    attempts: int = 1
    records_seen: int = 0
    records_imported: int = 0
    records_updated: int = 0
    records_deleted: int = 0
    duplicates: int = 0
    invalid: int = 0
    errors: int = 0
    error_message: str | None = None
    validation_issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        """Return report duration when the harvest has finished."""

        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    def finish(self, status: str, error_message: str | None = None) -> None:
        """Mark the report finished."""

        self.status = status
        self.error_message = error_message
        self.finished_at = datetime.now(UTC)

    def asdict(self) -> dict[str, Any]:
        """Return a JSON-serializable report dictionary."""

        payload = asdict(self)
        payload["started_at"] = self.started_at.isoformat()
        payload["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        payload["duration_seconds"] = self.duration_seconds
        payload["job_id"] = str(self.job_id)
        return payload


class HarvestEngine:
    """Run configured metadata connectors concurrently and persist normalized output."""

    def __init__(
        self,
        config: HarvestEngineConfig,
        store: HarvestStore | None = None,
        *,
        connector_factory: ConnectorFactory | None = None,
    ) -> None:
        self.config = config
        self.store = store or NullHarvestStore()
        self.connector_factory = connector_factory or self._default_connector_factory

    async def run_all(self) -> list[HarvestReport]:
        """Run all enabled connectors with bounded concurrency."""

        semaphore = asyncio.Semaphore(max(1, self.config.max_concurrent_connectors))

        async def run_with_limit(definition: HarvestConnectorDefinition) -> HarvestReport:
            async with semaphore:
                return await self.run_connector(definition.code)

        return await asyncio.gather(
            *(run_with_limit(definition) for definition in self.config.enabled_connectors)
        )

    async def run_connector(self, connector_code: str) -> HarvestReport:
        """Run one connector by code with retry support."""

        definition = self.config.connector_by_code(connector_code)
        attempts = max(1, self.config.job_max_attempts if self.config.retry_failed_jobs else 1)
        last_report: HarvestReport | None = None
        for attempt in range(1, attempts + 1):
            report = await self._run_connector_attempt(definition, attempt)
            if report.status == "succeeded":
                return report
            last_report = report
            if attempt < attempts:
                await self.store.log(
                    report.job_id,
                    level="warning",
                    event="harvest_retry_scheduled",
                    message=f"Retrying failed harvest attempt {attempt}",
                    context=report.asdict(),
                )
        assert last_report is not None
        return last_report

    async def _run_connector_attempt(
        self, definition: HarvestConnectorDefinition, attempt: int
    ) -> HarvestReport:
        """Run one connector attempt and return its report."""

        job_id = await self.store.start_job(definition, attempt)
        report = HarvestReport(
            connector_code=definition.code,
            job_id=job_id,
            status="running",
            started_at=datetime.now(UTC),
            attempts=attempt,
        )
        connector = self.connector_factory(definition.connector_type, definition)
        deduplicator = PublicationDeduplicator()
        await self.store.log(
            job_id,
            level="info",
            event="harvest_started",
            message=f"Started harvest for {definition.code}",
            context={"attempt": attempt, "connector_type": definition.connector_type},
        )
        try:
            async for raw_record in connector.collect(**definition.collect_kwargs()):
                report.records_seen += 1
                publication = connector.normalize(raw_record)
                validation = connector.validate(publication)
                if not validation.valid:
                    report.invalid += 1
                    report.validation_issues.extend(
                        _validation_issues_to_dict(validation.issues, publication.external_id)
                    )
                    await self.store.log(
                        job_id,
                        level="warning",
                        event="harvest_record_invalid",
                        message="Skipping invalid normalized publication",
                        context={"identifier": publication.external_id},
                    )
                    continue
                if deduplicator.seen(publication):
                    report.duplicates += 1
                    continue
                await self.store.publication_exists(publication)
                result = await self.store.store_publication(publication)
                if result == "inserted":
                    report.records_imported += 1
                elif result == "updated":
                    report.records_updated += 1
                elif result == "deleted":
                    report.records_deleted += 1
                else:
                    report.duplicates += 1
            report.finish("succeeded")
            await self.store.log(
                job_id,
                level="info",
                event="harvest_succeeded",
                message=f"Finished harvest for {definition.code}",
                context=report.asdict(),
            )
        except Exception as exc:  # noqa: BLE001 - jobs must be captured and reportable.
            report.errors += 1
            report.finish("failed", str(exc))
            await self.store.log(
                job_id,
                level="error",
                event="harvest_failed",
                message=str(exc),
                context=report.asdict(),
            )
        finally:
            close = getattr(connector, "aclose", None)
            if close:
                await close()
            await self.store.finish_job(job_id, report)
        return report

    def _default_connector_factory(
        self, connector_type: str, definition: HarvestConnectorDefinition
    ) -> MetadataConnector:
        """Create a connector from registry configuration."""

        return create_connector(connector_type, definition.to_connector_config())


def aggregate_reports(reports: Iterable[HarvestReport]) -> dict[str, Any]:
    """Generate a combined harvest report across connectors."""

    report_list = list(reports)
    return {
        "connectors": len(report_list),
        "succeeded": sum(1 for report in report_list if report.status == "succeeded"),
        "failed": sum(1 for report in report_list if report.status == "failed"),
        "records_seen": sum(report.records_seen for report in report_list),
        "records_imported": sum(report.records_imported for report in report_list),
        "records_updated": sum(report.records_updated for report in report_list),
        "records_deleted": sum(report.records_deleted for report in report_list),
        "duplicates": sum(report.duplicates for report in report_list),
        "invalid": sum(report.invalid for report in report_list),
        "errors": sum(report.errors for report in report_list),
        "reports": [report.asdict() for report in report_list],
    }


def _validation_issues_to_dict(
    issues: Iterable[ValidationIssue], identifier: str | None
) -> list[dict[str, Any]]:
    """Convert validation issues to serializable report entries."""

    return [
        {
            "identifier": identifier,
            "field": issue.field,
            "message": issue.message,
            "severity": issue.severity,
        }
        for issue in issues
    ]
