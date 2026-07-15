"""SQLAlchemy persistence adapter for the harvesting engine."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from researchhub_harvester.config import HarvestConnectorDefinition
from researchhub_harvester.connectors.base import NormalizedPublication
from researchhub_harvester.services.engine import HarvestReport, StoreResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from researchhub.application.harvest_persistence import (
    HarvestPersistenceContext,
    HarvestPersistenceService,
)
from researchhub.infrastructure.persistence.models import (
    Author,
    Connector,
    HarvestJob,
    HarvestLog,
    Keyword,
    Publication,
    PublicationAuthor,
    PublicationKeyword,
    QualityReport,
)
from researchhub.infrastructure.persistence.session import SessionLocal


class SQLAlchemyHarvestStore:
    """Database-backed store used by the harvesting engine."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
        *,
        existing_job_id: Any | None = None,
        dry_run: bool = False,
    ) -> None:
        self.session_factory = session_factory
        self._contexts_by_source: dict[str, HarvestPersistenceContext] = {}
        self.existing_job_id = existing_job_id
        self.dry_run = dry_run
        self.current_job_id: Any | None = existing_job_id

    async def start_job(self, definition: HarvestConnectorDefinition, attempt: int) -> Any:
        """Create a running harvest job and ensure a connector row exists."""

        self._contexts_by_source[definition.code] = self._context_from_definition(definition)
        async with self.session_factory() as session, session.begin():
            connector = await self._get_or_create_connector(session, definition)
            if self.existing_job_id is not None:
                job = await session.get(HarvestJob, self.existing_job_id)
                if job is None:
                    raise LookupError("Harvest job not found")
                job.status = "running"
                job.started_at = datetime.now(UTC)
                job.connector_id = connector.id
                self.current_job_id = job.id
                return job.id
            job = HarvestJob(
                connector_id=connector.id,
                status="running",
                started_at=datetime.now(UTC),
                since=definition.from_date,
                until=definition.until_date,
                metadata_json={
                    "attempt": attempt,
                    "connector_code": definition.code,
                    "connector_config": _definition_payload(definition),
                },
            )
            session.add(job)
            await session.flush()
            self.current_job_id = job.id
            return job.id

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

        async with self.session_factory() as session, session.begin():
            session.add(
                HarvestLog(
                    harvest_job_id=job_id,
                    level=level,
                    event=event,
                    message=message,
                    context=context or {},
                )
            )

    async def publication_exists(self, publication: NormalizedPublication) -> bool:
        """Return True when a publication already exists using pipeline identity matching."""

        async with self.session_factory() as session:
            service = HarvestPersistenceService(session)
            existing, _ = await service._match_existing_publication(publication)
            return existing is not None

    async def store_publication(self, publication: NormalizedPublication) -> StoreResult:
        """Persist one normalized publication through the metadata pipeline."""

        if await self._cancelled():
            raise RuntimeError("Harvest job was cancelled")
        if self.dry_run:
            return "deleted" if publication.is_deleted else "inserted"

        async with self.session_factory() as session:
            service = HarvestPersistenceService(session)
            result = await service.persist_many(
                [publication], self._context_for_publication(publication)
            )
        if result.created_count:
            return "inserted"
        if result.deleted_count:
            return "deleted"
        if result.updated_count or result.unchanged_count:
            return "updated"
        if result.duplicate_count:
            return "duplicate"
        if result.failed_count:
            error = result.errors[0]["error"] if result.errors else "unknown persistence failure"
            raise RuntimeError(error)
        return "duplicate"

    async def finish_job(self, job_id: Any, report: HarvestReport) -> None:
        """Persist final harvest job counters and serialized report."""

        async with self.session_factory() as session, session.begin():
            job = await session.get(HarvestJob, job_id)
            if job is None:
                return
            if job.status != "cancelled":
                job.status = "completed" if report.status == "succeeded" else report.status
            job.finished_at = report.finished_at or datetime.now(UTC)
            job.completed_at = job.finished_at
            job.duration_ms = (
                round((job.finished_at - job.started_at).total_seconds() * 1000)
                if job.started_at
                else None
            )
            job.records_seen = report.records_seen
            job.records_imported = report.records_imported
            job.records_updated = report.records_updated
            job.records_deleted = report.records_deleted
            job.error_count = report.errors
            job.error_message = report.error_message
            job.total_records = report.records_seen
            job.fetched_records = report.records_seen
            job.created_records = report.records_imported
            job.updated_records = report.records_updated
            job.deleted_records = report.records_deleted
            job.duplicate_records = report.duplicates
            job.failed_records = report.errors + report.invalid
            job.result_summary = report.asdict()
            job.metadata_json = {
                **(job.metadata_json or {}),
                "report": report.asdict(),
                "duplicates": report.duplicates,
                "invalid": report.invalid,
                "validation_issues": report.validation_issues,
            }
            connector = await session.get(Connector, job.connector_id)
            if connector:
                connector.last_harvested_at = job.finished_at
                if job.status == "completed":
                    connector.last_successful_harvest_at = job.finished_at
                    connector.status = "active" if connector.enabled else "disabled"
                    connector.last_error = None
                    connector.consecutive_failure_count = 0
                    connector.total_records_harvested += report.records_seen
                elif job.status != "cancelled":
                    connector.last_failed_harvest_at = job.finished_at
                    connector.status = "degraded"
                    connector.last_error = report.error_message
                    connector.consecutive_failure_count += 1

    async def _cancelled(self) -> bool:
        if self.current_job_id is None:
            return False
        async with self.session_factory() as session:
            status = await session.scalar(
                select(HarvestJob.status).where(HarvestJob.id == self.current_job_id)
            )
            return status == "cancelled"

    async def _get_or_create_connector(
        self, session: AsyncSession, definition: HarvestConnectorDefinition
    ) -> Connector:
        """Return an existing connector row or create it from JSON config."""

        result = await session.scalars(
            select(Connector).where(Connector.code == definition.code).limit(1)
        )
        connector = result.first()
        if connector:
            connector.name = definition.name
            connector.connector_type = definition.connector_type
            connector.base_url = definition.base_url
            connector.repository_id = definition.repository_id
            connector.university_id = definition.university_id
            connector.schedule = definition.schedule
            connector.config = _definition_payload(definition)
            return connector
        connector = Connector(
            code=definition.code,
            name=definition.name,
            connector_type=definition.connector_type,
            base_url=definition.base_url,
            repository_id=definition.repository_id,
            university_id=definition.university_id,
            schedule=definition.schedule,
            config=_definition_payload(definition),
        )
        session.add(connector)
        await session.flush()
        return connector

    def _context_from_definition(
        self, definition: HarvestConnectorDefinition
    ) -> HarvestPersistenceContext:
        """Build persistence context from connector JSON configuration."""

        return HarvestPersistenceContext(
            source=definition.code,
            source_type=definition.source_type,
            university_id=definition.university_id,
            repository_id=definition.repository_id,
            repository_name=definition.name,
            repository_base_url=definition.base_url,
            connector_code=definition.code,
        )

    def _context_for_publication(
        self, publication: NormalizedPublication
    ) -> HarvestPersistenceContext:
        """Return a stored context for publication source or a safe fallback."""

        return self._contexts_by_source.get(
            publication.source,
            HarvestPersistenceContext(
                source=publication.source,
                source_type=publication.source_type,
                repository_name=publication.repository,
                connector_code=publication.source,
            ),
        )

    async def _find_publication(
        self, session: AsyncSession, publication: NormalizedPublication
    ) -> Publication | None:
        """Find an existing publication by DOI or source identifier."""

        if publication.doi:
            result = await session.scalars(
                select(Publication).where(Publication.doi == publication.doi).limit(1)
            )
            found = result.first()
            if found:
                return found
        if publication.external_id:
            result = await session.scalars(
                select(Publication)
                .where(
                    Publication.source == publication.source,
                    Publication.external_id == publication.external_id,
                )
                .limit(1)
            )
            return result.first()
        return None

    def _new_publication(self, publication: NormalizedPublication) -> Publication:
        """Create a SQLAlchemy publication from normalized metadata."""

        stored = Publication(
            title=publication.title, source=publication.source, source_type=publication.source_type
        )
        self._apply_publication_fields(stored, publication)
        return stored

    def _apply_publication_fields(
        self, stored: Publication, publication: NormalizedPublication
    ) -> None:
        """Copy normalized publication fields onto an ORM publication."""

        stored.external_id = publication.external_id
        stored.title = publication.title
        stored.abstract = publication.abstract
        stored.affiliations = publication.affiliations
        stored.publisher = publication.publisher
        stored.publication_date = publication.publication_date
        stored.publication_year = publication.publication_year
        stored.subjects = publication.subjects
        stored.language = publication.language
        stored.doi = publication.doi
        stored.issn = publication.issn
        stored.isbn = publication.isbn
        stored.license = publication.license
        stored.article_url = publication.article_url
        stored.pdf_url = publication.pdf_url
        stored.repository_identifier = publication.repository_identifier
        stored.source = publication.source
        stored.source_type = publication.source_type
        stored.harvested_at = publication.harvested_at
        stored.quality_score = Decimal(str(publication.quality_score)).quantize(Decimal("0.01"))
        stored.is_deleted = publication.is_deleted
        stored.raw_record = publication.raw_record
        stored.metadata_json = {
            **(stored.metadata_json or {}),
            "journal": publication.journal,
            "repository": publication.repository,
            "orcid": publication.orcid,
        }

    async def _attach_authors(
        self,
        session: AsyncSession,
        stored: Publication,
        publication: NormalizedPublication,
    ) -> None:
        """Attach missing authors to a stored publication."""

        existing_author_ids = await self._existing_author_ids(session, stored.id)
        for index, author_name in enumerate(publication.authors, start=1):
            author = await self._get_or_create_author(session, author_name)
            if author.id in existing_author_ids:
                continue
            session.add(
                PublicationAuthor(
                    publication_id=stored.id,
                    author_id=author.id,
                    author_order=index,
                    affiliation=publication.affiliations[index - 1]
                    if index <= len(publication.affiliations)
                    else None,
                    orcid=publication.orcid,
                )
            )

    async def _attach_keywords(
        self,
        session: AsyncSession,
        stored: Publication,
        publication: NormalizedPublication,
    ) -> None:
        """Attach missing keywords to a stored publication."""

        existing_keyword_ids = await self._existing_keyword_ids(session, stored.id)
        for term in publication.keywords:
            keyword = await self._get_or_create_keyword(session, term)
            if keyword.id in existing_keyword_ids:
                continue
            session.add(PublicationKeyword(publication_id=stored.id, keyword_id=keyword.id))

    async def _get_or_create_author(self, session: AsyncSession, full_name: str) -> Author:
        """Return an existing author by normalized name or create one."""

        normalized = _normalize_text(full_name)
        result = await session.scalars(
            select(Author).where(Author.normalized_name == normalized).limit(1)
        )
        author = result.first()
        if author:
            return author
        author = Author(full_name=full_name.strip(), normalized_name=normalized)
        session.add(author)
        await session.flush()
        return author

    async def _get_or_create_keyword(self, session: AsyncSession, term: str) -> Keyword:
        """Return an existing keyword by normalized term or create one."""

        normalized = _normalize_text(term)
        result = await session.scalars(
            select(Keyword).where(Keyword.normalized_term == normalized).limit(1)
        )
        keyword = result.first()
        if keyword:
            return keyword
        keyword = Keyword(term=term.strip(), normalized_term=normalized)
        session.add(keyword)
        await session.flush()
        return keyword

    async def _existing_author_ids(self, session: AsyncSession, publication_id: Any) -> set[Any]:
        """Return author ids already attached to a publication."""

        rows = await session.scalars(
            select(PublicationAuthor.author_id).where(
                PublicationAuthor.publication_id == publication_id
            )
        )
        return set(rows.all())

    async def _existing_keyword_ids(self, session: AsyncSession, publication_id: Any) -> set[Any]:
        """Return keyword ids already attached to a publication."""

        rows = await session.scalars(
            select(PublicationKeyword.keyword_id).where(
                PublicationKeyword.publication_id == publication_id
            )
        )
        return set(rows.all())

    def _add_quality_report(
        self,
        session: AsyncSession,
        stored: Publication,
        publication: NormalizedPublication,
    ) -> None:
        """Persist metadata quality details when available."""

        quality = publication.raw_record.get("metadata_quality", {})
        session.add(
            QualityReport(
                publication_id=stored.id,
                score=Decimal(str(publication.quality_score)).quantize(Decimal("0.01")),
                missing_fields=list(quality.get("missing_fields", [])),
                warnings=list(quality.get("warnings", [])),
                metadata_json={"source": publication.source},
            )
        )


def _definition_payload(definition: HarvestConnectorDefinition) -> dict[str, Any]:
    """Serialize a connector definition for JSONB storage."""

    payload = asdict(definition)
    for key in ("from_date", "until_date"):
        payload[key] = payload[key].isoformat() if payload[key] else None
    for key in ("connector_id", "university_id", "repository_id"):
        payload[key] = str(payload[key]) if payload[key] else None
    return payload


def _normalize_text(value: str) -> str:
    """Normalize names and terms for lookup."""

    return " ".join(value.casefold().strip().split())
