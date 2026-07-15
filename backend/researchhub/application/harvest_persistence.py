"""Metadata persistence pipeline for normalized connector output."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Literal
from uuid import UUID

from researchhub_harvester.connectors.base import PublicationMetadata
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.infrastructure.persistence.models import (
    Author,
    Journal,
    Keyword,
    License,
    MetadataHistory,
    Publication,
    PublicationAuthor,
    PublicationKeyword,
    PublicationType,
    Repository,
    University,
)
from researchhub.infrastructure.persistence.repositories import (
    AuthorRepository,
    InstitutionalRepositoryRepository,
    JournalRepository,
    KeywordRepository,
    LicenseRepository,
    MetadataHistoryRepository,
    PublicationRepository,
    PublicationTypeRepository,
    UniversityRepository,
)
from researchhub.infrastructure.persistence.transactions import transaction

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

PersistenceAction = Literal["created", "updated", "unchanged", "deleted", "duplicate", "failed"]

IMPORTANT_PUBLICATION_FIELDS = (
    "external_id",
    "title",
    "abstract",
    "journal_id",
    "publication_type_id",
    "license_id",
    "publisher",
    "publication_date",
    "publication_year",
    "language",
    "doi",
    "issn",
    "isbn",
    "license",
    "article_url",
    "pdf_url",
    "repository_id",
    "repository_identifier",
    "repository_datestamp",
    "source",
    "source_type",
    "quality_score",
    "is_deleted",
)


@dataclass(frozen=True, slots=True)
class HarvestPersistenceContext:
    """Institutional context for a batch of normalized publication metadata."""

    source: str
    source_type: str
    university_id: UUID | None = None
    university_code: str | None = None
    university_name: str | None = None
    repository_id: UUID | None = None
    repository_name: str | None = None
    repository_base_url: str | None = None
    connector_code: str | None = None


@dataclass(slots=True)
class HarvestPersistenceResult:
    """Aggregate result returned by the metadata persistence pipeline."""

    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    deleted_count: int = 0
    failed_count: int = 0
    duplicate_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def record(self, action: PersistenceAction) -> None:
        """Increment the counter corresponding to a persistence action."""

        if action == "created":
            self.created_count += 1
        elif action == "updated":
            self.updated_count += 1
        elif action == "unchanged":
            self.unchanged_count += 1
        elif action == "deleted":
            self.deleted_count += 1
        elif action == "duplicate":
            self.duplicate_count += 1
        elif action == "failed":
            self.failed_count += 1

    def asdict(self) -> dict[str, Any]:
        """Return a JSON-serializable result payload."""

        return {
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "unchanged_count": self.unchanged_count,
            "deleted_count": self.deleted_count,
            "failed_count": self.failed_count,
            "duplicate_count": self.duplicate_count,
            "errors": self.errors,
        }


@dataclass(frozen=True, slots=True)
class PersistenceOutcome:
    """Per-record persistence outcome."""

    action: PersistenceAction
    publication_id: UUID | None = None
    matched_by: str | None = None


class HarvestPersistenceService:
    """Persist normalized publication metadata into the research metadata graph."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.universities = UniversityRepository(session)
        self.repositories = InstitutionalRepositoryRepository(session)
        self.publications = PublicationRepository(session)
        self.authors = AuthorRepository(session)
        self.keywords = KeywordRepository(session)
        self.journals = JournalRepository(session)
        self.publication_types = PublicationTypeRepository(session)
        self.licenses = LicenseRepository(session)
        self.history = MetadataHistoryRepository(session)

    async def persist_many(
        self,
        publications: Iterable[PublicationMetadata],
        context: HarvestPersistenceContext,
    ) -> HarvestPersistenceResult:
        """Persist a batch of normalized publication metadata."""

        result = HarvestPersistenceResult()
        seen_batch_keys: set[str] = set()
        for metadata in publications:
            batch_key = self._batch_key(metadata)
            if batch_key in seen_batch_keys:
                result.record("duplicate")
                self._log("info", "harvest_persistence_batch_duplicate", identifier=metadata.external_id)
                continue
            seen_batch_keys.add(batch_key)
            try:
                outcome = await self.persist_one(metadata, context)
                result.record(outcome.action)
            except Exception as exc:  # noqa: BLE001 - persistence pipeline reports per-record failures.
                result.record("failed")
                result.errors.append({"identifier": metadata.external_id, "error": str(exc)})
                self._log(
                    "error",
                    "harvest_persistence_failed",
                    identifier=metadata.external_id,
                    error=str(exc),
                )
        return result

    async def persist_one(
        self,
        metadata: PublicationMetadata,
        context: HarvestPersistenceContext,
    ) -> PersistenceOutcome:
        """Persist one normalized publication with explicit transaction boundaries."""

        async with transaction(self.session):
            university = await self._resolve_university(context)
            repository = await self._resolve_repository(context, university, metadata)
            journal = await self._resolve_journal(metadata, university)
            publication_type = await self._resolve_publication_type(metadata)
            license_record = await self._resolve_license(metadata)
            existing, matched_by = await self._match_existing_publication(metadata)

            if metadata.is_deleted:
                outcome = await self._persist_deleted_record(existing, metadata, matched_by)
                self._log(
                    "info",
                    "harvest_persistence_deleted_record",
                    identifier=metadata.external_id,
                    action=outcome.action,
                    matched_by=outcome.matched_by,
                )
                return outcome

            if existing is None:
                stored = self._new_publication(metadata)
                self.session.add(stored)
                await self.session.flush()
                action: PersistenceAction = "created"
            else:
                stored = existing
                action = "updated"

            changed = await self._apply_publication_metadata(
                stored,
                metadata,
                repository=repository,
                journal=journal,
                publication_type=publication_type,
                license_record=license_record,
            )
            await self._sync_authors(stored, metadata)
            await self._sync_keywords(stored, metadata)
            if action == "updated" and not changed:
                action = "unchanged"

            self._log(
                "info",
                "harvest_persistence_publication_saved",
                identifier=metadata.external_id,
                publication_id=str(stored.id),
                action=action,
                matched_by=matched_by,
            )
            return PersistenceOutcome(action=action, publication_id=stored.id, matched_by=matched_by)

    async def _resolve_university(self, context: HarvestPersistenceContext) -> University:
        """Resolve or create the university for the harvest context."""

        if context.university_id:
            university = await self.universities.get(context.university_id)
            if university:
                return university
        code = (context.university_code or f"AUTO-{context.source}")[:40].upper()
        existing = await self.universities.get_by_code(code)
        if existing:
            return existing
        name = context.university_name or f"Unknown institution for {context.source}"
        university = University(code=code, name=name, country="Ethiopia")
        await self.universities.add(university)
        self._log("info", "harvest_persistence_university_created", university_code=code)
        return university

    async def _resolve_repository(
        self,
        context: HarvestPersistenceContext,
        university: University,
        metadata: PublicationMetadata,
    ) -> Repository:
        """Resolve or create the repository for the harvest context."""

        if context.repository_id:
            repository = await self.repositories.get(context.repository_id)
            if repository:
                return repository
        repository_name = context.repository_name or metadata.repository or context.source
        candidates = await self.repositories.list(
            filters=None,
            limit=500,
            offset=0,
        )
        for repository in candidates:
            if repository.university_id == university.id and _normalize(repository.name) == _normalize(repository_name):
                if context.repository_base_url and not repository.base_url:
                    repository.base_url = context.repository_base_url
                    repository.oai_endpoint = context.repository_base_url
                return repository
            if context.repository_base_url and repository.base_url == context.repository_base_url:
                return repository
        repository_url = context.repository_base_url or metadata.article_url
        if not repository_url:
            raise ValueError("Repository URL is required to create a catalogue entry")
        repository = Repository(
            university_id=university.id,
            name=repository_name,
            platform=context.source_type,
            base_url=repository_url,
            oai_endpoint=context.repository_base_url,
            metadata_formats=["oai_dc"],
            metadata_json={"created_by": "harvest_persistence_service"},
        )
        await self.repositories.add(repository)
        self._log("info", "harvest_persistence_repository_created", repository_name=repository_name)
        return repository

    async def _resolve_journal(
        self, metadata: PublicationMetadata, university: University
    ) -> Journal | None:
        """Resolve or create a journal without duplicating normalized names."""

        journal_name = metadata.journal or _metadata_first(metadata, "source")
        if not journal_name:
            return None
        if metadata.issn:
            existing_by_issn = await self.journals.get_by_issn(metadata.issn)
            if existing_by_issn:
                return existing_by_issn
        normalized_name = _normalize(journal_name)
        existing = await self.journals.get_by_normalized_name(normalized_name, university.id)
        if existing:
            return existing
        journal = Journal(
            university_id=university.id,
            name=journal_name.strip(),
            normalized_name=normalized_name,
            issn=metadata.issn,
            publisher=metadata.publisher,
        )
        await self.journals.add(journal)
        return journal

    async def _resolve_publication_type(
        self, metadata: PublicationMetadata
    ) -> PublicationType | None:
        """Resolve or create publication type vocabulary values."""

        type_name = _metadata_first(metadata, "type") or _metadata_first(metadata, "publication_type")
        if not type_name:
            return None
        normalized_name = _normalize(type_name)
        existing = await self.publication_types.get_by_normalized_name(normalized_name)
        if existing:
            return existing
        publication_type = PublicationType(name=type_name.strip(), normalized_name=normalized_name)
        await self.publication_types.add(publication_type)
        return publication_type

    async def _resolve_license(self, metadata: PublicationMetadata) -> License | None:
        """Resolve or create license vocabulary values."""

        license_name = metadata.license or _metadata_first(metadata, "rights") or _metadata_first(metadata, "license")
        if not license_name:
            return None
        normalized_name = _normalize(license_name)
        existing = await self.licenses.get_by_normalized_name(normalized_name)
        if existing:
            return existing
        license_record = License(name=license_name.strip(), normalized_name=normalized_name)
        await self.licenses.add(license_record)
        return license_record

    async def _match_existing_publication(
        self, metadata: PublicationMetadata
    ) -> tuple[Publication | None, str | None]:
        """Match existing publications using the required identity order."""

        if metadata.doi:
            existing = await self.publications.get_by_doi(metadata.doi)
            if existing:
                return existing, "doi"
        if metadata.source and metadata.external_id:
            existing = await self.publications.get_by_source_identifier(
                source=metadata.source,
                external_id=metadata.external_id,
            )
            if existing:
                return existing, "source_external_id"
        normalized_title = _normalize_title(metadata.title)
        first_author = _normalize(metadata.authors[0]) if metadata.authors else None
        existing = await self.publications.find_by_title_year_first_author(
            normalized_title=normalized_title,
            publication_year=metadata.publication_year,
            first_author_normalized=first_author,
        )
        if existing:
            return existing, "title_year_first_author"
        existing = await self._title_similarity_match(metadata, normalized_title)
        if existing:
            return existing, "title_similarity"
        return None, None

    async def _title_similarity_match(
        self, metadata: PublicationMetadata, normalized_title: str
    ) -> Publication | None:
        """Find a candidate publication using normalized title similarity."""

        if not normalized_title:
            return None
        candidates = await self.publications.title_similarity_candidates(
            publication_year=metadata.publication_year,
            limit=100,
        )
        best: tuple[float, Publication | None] = (0.0, None)
        for candidate in candidates:
            candidate_title = candidate.normalized_title or _normalize_title(candidate.title)
            score = SequenceMatcher(None, normalized_title, candidate_title).ratio()
            if score > best[0]:
                best = (score, candidate)
        return best[1] if best[0] >= 0.92 else None

    async def _persist_deleted_record(
        self,
        existing: Publication | None,
        metadata: PublicationMetadata,
        matched_by: str | None,
    ) -> PersistenceOutcome:
        """Mark matched deleted records while preserving tombstone metadata."""

        if existing is None:
            tombstone = self._new_publication(metadata)
            tombstone.is_deleted = True
            tombstone.raw_record = metadata.raw_record
            tombstone.normalized_record = _normalized_record(metadata)
            tombstone.metadata_json = {
                **(tombstone.metadata_json or {}),
                "deleted_without_existing_match": True,
            }
            self.session.add(tombstone)
            await self.session.flush()
            return PersistenceOutcome(action="deleted", publication_id=tombstone.id, matched_by=None)

        old_value = existing.is_deleted
        existing.is_deleted = True
        existing.raw_record = metadata.raw_record
        existing.normalized_record = _normalized_record(metadata)
        existing.repository_datestamp = metadata.updated_at
        await self._add_history(existing.id, metadata.source, "is_deleted", old_value, True)
        return PersistenceOutcome(action="deleted", publication_id=existing.id, matched_by=matched_by)

    def _new_publication(self, metadata: PublicationMetadata) -> Publication:
        """Create a publication shell from metadata."""

        return Publication(
            title=metadata.title,
            normalized_title=_normalize_title(metadata.title),
            source=metadata.source,
            source_type=metadata.source_type,
        )

    async def _apply_publication_metadata(
        self,
        stored: Publication,
        metadata: PublicationMetadata,
        *,
        repository: Repository,
        journal: Journal | None,
        publication_type: PublicationType | None,
        license_record: License | None,
    ) -> bool:
        """Apply normalized fields and record metadata history for changes."""

        new_values = {
            "external_id": metadata.external_id,
            "title": metadata.title,
            "normalized_title": _normalize_title(metadata.title),
            "abstract": metadata.abstract,
            "journal_id": journal.id if journal else None,
            "publication_type_id": publication_type.id if publication_type else None,
            "license_id": license_record.id if license_record else None,
            "publisher": metadata.publisher,
            "publication_date": metadata.publication_date,
            "publication_year": metadata.publication_year,
            "subjects": metadata.subjects,
            "language": metadata.language,
            "doi": metadata.doi,
            "issn": metadata.issn,
            "isbn": metadata.isbn,
            "license": metadata.license,
            "article_url": metadata.article_url,
            "pdf_url": metadata.pdf_url,
            "source_urls": _source_urls(metadata),
            "repository_id": repository.id,
            "repository_identifier": metadata.repository_identifier,
            "repository_datestamp": metadata.updated_at,
            "source": metadata.source,
            "source_type": metadata.source_type,
            "harvested_at": metadata.harvested_at,
            "quality_score": Decimal(str(metadata.quality_score)).quantize(Decimal("0.01")),
            "is_deleted": metadata.is_deleted,
            "raw_record": metadata.raw_record,
            "normalized_record": _normalized_record(metadata),
            "metadata_json": {
                **(stored.metadata_json or {}),
                "affiliations": metadata.affiliations,
                "repository": metadata.repository,
                "orcid": metadata.orcid,
            },
        }
        changed = False
        for field_name, new_value in new_values.items():
            old_value = getattr(stored, field_name)
            if old_value != new_value:
                if field_name in IMPORTANT_PUBLICATION_FIELDS:
                    await self._add_history(
                        stored.id, metadata.source, field_name, old_value, new_value
                    )
                setattr(stored, field_name, new_value)
                changed = True
        return changed

    async def _sync_authors(self, stored: Publication, metadata: PublicationMetadata) -> None:
        """Resolve or create authors and attach them without duplicates."""

        existing_ids = await self._existing_author_ids(stored.id)
        for index, name in enumerate(metadata.authors, start=1):
            author = await self._resolve_author(name, metadata.orcid if index == 1 else None)
            if author.id in existing_ids:
                continue
            self.session.add(
                PublicationAuthor(
                    publication_id=stored.id,
                    author_id=author.id,
                    author_order=index,
                    affiliation=metadata.affiliations[index - 1]
                    if index <= len(metadata.affiliations)
                    else None,
                    orcid=metadata.orcid if index == 1 else None,
                )
            )
            # Track pending associations too. A later author-resolution query
            # can trigger autoflush before this method reaches the database again.
            existing_ids.add(author.id)

    async def _sync_keywords(self, stored: Publication, metadata: PublicationMetadata) -> None:
        """Resolve or create keywords and attach them without duplicates."""

        existing_ids = await self._existing_keyword_ids(stored.id)
        for term in metadata.keywords:
            keyword = await self._resolve_keyword(term)
            if keyword.id in existing_ids:
                continue
            self.session.add(PublicationKeyword(publication_id=stored.id, keyword_id=keyword.id))
            existing_ids.add(keyword.id)

    async def _resolve_author(self, full_name: str, orcid: str | None) -> Author:
        """Resolve or create an author without duplicates."""

        if orcid:
            existing = await self.authors.get_by_orcid(orcid)
            if existing:
                return existing
        normalized_name = _normalize(full_name)
        existing = await self.authors.get_by_normalized_name(normalized_name)
        if existing:
            return existing
        author = Author(full_name=full_name.strip(), normalized_name=normalized_name, orcid=orcid)
        await self.authors.add(author)
        return author

    async def _resolve_keyword(self, term: str) -> Keyword:
        """Resolve or create a keyword without duplicates."""

        normalized_term = _normalize(term)
        existing = await self.keywords.get_by_normalized_term(normalized_term)
        if existing:
            return existing
        keyword = Keyword(term=term.strip(), normalized_term=normalized_term)
        await self.keywords.add(keyword)
        return keyword

    async def _existing_author_ids(self, publication_id: UUID) -> set[UUID]:
        """Return author ids already attached to the publication."""

        result = await self.session.scalars(
            PublicationAuthor.__table__.select()
            .with_only_columns(PublicationAuthor.author_id)
            .where(PublicationAuthor.publication_id == publication_id)
        )
        return set(result.all())

    async def _existing_keyword_ids(self, publication_id: UUID) -> set[UUID]:
        """Return keyword ids already attached to the publication."""

        result = await self.session.scalars(
            PublicationKeyword.__table__.select()
            .with_only_columns(PublicationKeyword.keyword_id)
            .where(PublicationKeyword.publication_id == publication_id)
        )
        return set(result.all())

    async def _add_history(
        self,
        publication_id: UUID | None,
        source: str,
        field_name: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """Persist field-level metadata history."""

        if publication_id is None:
            return
        await self.history.add(
            MetadataHistory(
                publication_id=publication_id,
                source=source,
                field_name=field_name,
                old_value=_json_safe(old_value),
                new_value=_json_safe(new_value),
                changed_by="harvest_persistence_service",
            )
        )

    def _batch_key(self, metadata: PublicationMetadata) -> str:
        """Return an in-batch duplicate key."""

        if metadata.doi:
            return f"doi:{metadata.doi.casefold()}"
        if metadata.external_id:
            return f"source:{metadata.source}:{metadata.external_id}"
        first_author = _normalize(metadata.authors[0]) if metadata.authors else ""
        return f"title:{_normalize_title(metadata.title)}:{metadata.publication_year}:{first_author}"

    def _log(self, level: str, event: str, **context: Any) -> None:
        """Emit structured logs for the persistence pipeline."""

        getattr(logger, level, logger.info)(
            event,
            extra={
                "researchhub": {
                    "event": event,
                    "component": "harvest_persistence_service",
                    **context,
                }
            },
        )


def _metadata_first(metadata: PublicationMetadata, key: str) -> str | None:
    """Return the first raw metadata value for a key."""

    raw_metadata = metadata.raw_record.get("metadata", {})
    values = raw_metadata.get(key, [])
    if isinstance(values, list):
        return next((str(value) for value in values if value), None)
    return str(values) if values else None


def _source_urls(metadata: PublicationMetadata) -> list[str]:
    """Return source URLs from normalized URL fields and raw identifiers."""

    urls = [url for url in [metadata.article_url, metadata.pdf_url] if url]
    raw_identifiers = metadata.raw_record.get("metadata", {}).get("identifier", [])
    for value in raw_identifiers:
        text = str(value)
        if text.startswith(("http://", "https://")) and text not in urls:
            urls.append(text)
    return urls


def _normalized_record(metadata: PublicationMetadata) -> dict[str, Any]:
    """Return normalized metadata stored for provenance and audit."""

    return {
        "external_id": metadata.external_id,
        "title": metadata.title,
        "abstract": metadata.abstract,
        "authors": metadata.authors,
        "affiliations": metadata.affiliations,
        "journal": metadata.journal,
        "publisher": metadata.publisher,
        "publication_date": metadata.publication_date.isoformat() if metadata.publication_date else None,
        "publication_year": metadata.publication_year,
        "keywords": metadata.keywords,
        "subjects": metadata.subjects,
        "language": metadata.language,
        "doi": metadata.doi,
        "orcid": metadata.orcid,
        "issn": metadata.issn,
        "isbn": metadata.isbn,
        "license": metadata.license,
        "article_url": metadata.article_url,
        "pdf_url": metadata.pdf_url,
        "repository": metadata.repository,
        "repository_identifier": metadata.repository_identifier,
        "source": metadata.source,
        "source_type": metadata.source_type,
        "harvested_at": metadata.harvested_at.isoformat(),
        "repository_datestamp": metadata.updated_at.isoformat(),
        "quality_score": metadata.quality_score,
        "is_deleted": metadata.is_deleted,
    }


def _json_safe(value: Any) -> Any:
    """Convert common non-JSON scalar values to JSON-friendly values."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _normalize(value: str | None) -> str:
    """Normalize identity text for matching."""

    if not value:
        return ""
    return " ".join(value.casefold().strip().split())


def _normalize_title(value: str | None) -> str:
    """Normalize publication titles for identity matching."""

    normalized = _normalize(value)
    normalized = re.sub(r"[^\w\s]", "", normalized)
    return " ".join(normalized.split())
