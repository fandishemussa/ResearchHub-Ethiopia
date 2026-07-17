"""Metadata quality assessment use cases for ResearchHub Ethiopia.

The service evaluates normalized publication records across configurable quality
dimensions, stores current and historical reports, and exposes read models used
by the quality API. URL reachability checks are asynchronous and deliberately
disabled by default so ordinary harvests do not depend on outbound network IO.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from researchhub.core.logging import get_logger
from researchhub.domain.value_objects import normalize_doi, normalize_orcid
from researchhub.infrastructure.persistence.models import (
    Author,
    Publication,
    PublicationAuthor,
    PublicationKeyword,
    QualityReport,
)
from researchhub.infrastructure.persistence.repositories import (
    Page,
    Pagination,
    PublicationRepository,
    QualityReportFilters,
    QualityReportRepository,
)
from researchhub.infrastructure.persistence.transactions import transaction

RULESET_VERSION = "metadata-quality-v1"
DIMENSIONS = (
    "completeness",
    "validity",
    "consistency",
    "uniqueness",
    "timeliness",
    "accessibility",
)
DEFAULT_WEIGHTS: dict[str, float] = {
    "completeness": 0.30,
    "validity": 0.20,
    "consistency": 0.15,
    "uniqueness": 0.15,
    "timeliness": 0.10,
    "accessibility": 0.10,
}
PLACEHOLDER_TEXT = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "none",
    "null",
    "tbd",
    "test",
    "untitled",
    "no title",
    "not available",
    "no abstract",
    "no abstract available",
    "abstract",
}
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$", re.IGNORECASE)
HTTP_SCHEMES = {"http", "https"}
LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MetadataQualityWeights:
    """Configurable weights for the six quality dimensions."""

    completeness: float = DEFAULT_WEIGHTS["completeness"]
    validity: float = DEFAULT_WEIGHTS["validity"]
    consistency: float = DEFAULT_WEIGHTS["consistency"]
    uniqueness: float = DEFAULT_WEIGHTS["uniqueness"]
    timeliness: float = DEFAULT_WEIGHTS["timeliness"]
    accessibility: float = DEFAULT_WEIGHTS["accessibility"]

    @classmethod
    def from_mapping(cls, values: Mapping[str, float] | None = None) -> MetadataQualityWeights:
        """Create weights from a partial mapping and normalize the total to one."""

        raw = {**DEFAULT_WEIGHTS, **(dict(values or {}))}
        total = sum(max(float(raw[name]), 0.0) for name in DIMENSIONS)
        if total <= 0:
            raw = DEFAULT_WEIGHTS.copy()
            total = sum(raw.values())
        normalized = {name: max(float(raw[name]), 0.0) / total for name in DIMENSIONS}
        return cls(**normalized)

    def as_dict(self) -> dict[str, float]:
        """Return the normalized weight mapping."""

        return {name: getattr(self, name) for name in DIMENSIONS}


@dataclass(slots=True)
class QualityAssessment:
    """In-memory result produced by the quality rules engine."""

    publication_id: UUID
    completeness_score: Decimal
    validity_score: Decimal
    consistency_score: Decimal
    uniqueness_score: Decimal
    timeliness_score: Decimal
    accessibility_score: Decimal
    final_score: Decimal
    grade: str
    missing_fields: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    issue_types: list[str] = field(default_factory=list)
    assessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ruleset_version: str = RULESET_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QualityIssue:
    """Flattened quality issue used by the API issue listing."""

    publication_id: UUID
    report_id: UUID
    grade: str
    final_score: Decimal
    issue_type: str
    category: str
    message: str
    assessed_at: datetime


@dataclass(frozen=True, slots=True)
class QualitySummary:
    """Aggregate quality metrics for dashboards and administration."""

    total_reports: int
    assessed_publications: int
    active_publications: int
    deleted_publications: int
    average_final_score: Decimal
    grade_distribution: dict[str, int]
    dimension_averages: dict[str, Decimal]
    generated_at: datetime
    ruleset_version: str


@dataclass(frozen=True, slots=True)
class RecalculateAllResult:
    """Batch recalculation result."""

    assessed_count: int
    created_count: int
    unchanged_count: int
    failed_count: int


class MetadataQualityService:
    """Evaluate, persist, and query publication metadata quality."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        weights: Mapping[str, float] | None = None,
        check_url_reachability: bool = False,
        url_timeout_seconds: float = 3.0,
    ) -> None:
        self.session = session
        self.publications = PublicationRepository(session)
        self.reports = QualityReportRepository(session)
        self.weights = MetadataQualityWeights.from_mapping(weights)
        self.check_url_reachability = check_url_reachability
        self.url_timeout_seconds = url_timeout_seconds

    async def assess_publication(self, publication: Publication) -> QualityAssessment:
        """Evaluate a publication without persisting the report."""

        collector = _IssueCollector()
        authors = _authors_for(publication)
        keywords = _keywords_for(publication)
        source_urls = _source_urls_for(publication)

        completeness = self._score_completeness(publication, authors, collector)
        validity = self._score_validity(publication, authors, source_urls, collector)
        consistency = self._score_consistency(publication, keywords, collector)
        uniqueness = self._score_uniqueness(authors, keywords, source_urls, collector)
        timeliness = self._score_timeliness(publication, collector)
        accessibility = self._score_accessibility(publication, source_urls, collector)

        if publication.is_deleted:
            collector.add_warning(
                "record_deleted",
                "Deleted source records are assessed separately from active averages.",
            )

        if self.check_url_reachability:
            await self._evaluate_url_reachability(source_urls, collector)

        scores = {
            "completeness": completeness,
            "validity": validity,
            "consistency": consistency,
            "uniqueness": uniqueness,
            "timeliness": timeliness,
            "accessibility": accessibility,
        }
        final_score = _decimal_score(
            sum(float(scores[name]) * self.weights.as_dict()[name] for name in DIMENSIONS)
        )

        return QualityAssessment(
            publication_id=publication.id,
            completeness_score=completeness,
            validity_score=validity,
            consistency_score=consistency,
            uniqueness_score=uniqueness,
            timeliness_score=timeliness,
            accessibility_score=accessibility,
            final_score=final_score,
            grade=grade_for_score(final_score),
            missing_fields=collector.missing_fields,
            validation_errors=collector.validation_errors,
            warnings=collector.warnings,
            recommendations=collector.recommendations,
            issue_types=collector.issue_types,
            metadata={
                "weights": self.weights.as_dict(),
                "source": publication.source,
                "source_type": publication.source_type,
                "is_deleted": publication.is_deleted,
            },
        )

    async def recalculate_publication(self, publication_id: UUID) -> QualityReport | None:
        """Assess and persist the current report for one publication."""

        publication = await self._load_publication(publication_id)
        if publication is None:
            return None
        assessment = await self.assess_publication(publication)
        async with transaction(self.session):
            report, created = await self._persist_assessment(publication, assessment)
        LOGGER.info(
            "metadata_quality_publication_assessed",
            publication_id=str(publication_id),
            grade=report.grade,
            final_score=str(report.final_score),
            report_created=created,
        )
        return report

    async def recalculate_all(
        self,
        *,
        is_deleted: bool | None = False,
        limit: int = 500,
        offset: int = 0,
    ) -> RecalculateAllResult:
        """Assess a bounded batch of publications and persist changed reports."""

        page = Pagination(limit=limit, offset=offset).normalized()
        statement = (
            select(Publication)
            .options(
                selectinload(Publication.authors).selectinload(PublicationAuthor.author),
                selectinload(Publication.keywords).selectinload(PublicationKeyword.keyword),
                selectinload(Publication.journal),
                selectinload(Publication.license_record),
                selectinload(Publication.repository),
            )
            .limit(page.limit)
            .offset(page.offset)
        )
        if is_deleted is not None:
            statement = statement.where(Publication.is_deleted.is_(is_deleted))
        result = await self.session.scalars(statement)

        assessed = created = unchanged = failed = 0
        for publication in result.unique().all():
            assessed += 1
            try:
                assessment = await self.assess_publication(publication)
                async with transaction(self.session):
                    _, report_created = await self._persist_assessment(publication, assessment)
                if report_created:
                    created += 1
                else:
                    unchanged += 1
            except Exception as exc:  # pragma: no cover - defensive operational guard
                failed += 1
                LOGGER.warning(
                    "metadata_quality_assessment_failed",
                    publication_id=str(publication.id),
                    error=str(exc),
                )
        return RecalculateAllResult(
            assessed_count=assessed,
            created_count=created,
            unchanged_count=unchanged,
            failed_count=failed,
        )

    async def get_publication_report(self, publication_id: UUID) -> QualityReport | None:
        """Return the current quality report for a publication."""

        return await self.reports.latest_for_publication(publication_id)

    async def latest_reports(
        self,
        filters: QualityReportFilters | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[QualityReport]:
        """Return a filtered page of current quality reports."""

        return await self.reports.paginate(
            filters or QualityReportFilters(), limit=limit, offset=offset
        )

    async def low_quality_reports(
        self,
        filters: QualityReportFilters | None = None,
        *,
        threshold: float = 70.0,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[QualityReport]:
        """Return reports below the configured threshold."""

        filters = filters or QualityReportFilters()
        max_score = threshold if filters.max_score is None else min(filters.max_score, threshold)
        low_quality_filters = QualityReportFilters(
            publication_id=filters.publication_id,
            grade=filters.grade,
            min_score=filters.min_score,
            max_score=max_score,
            issue_type=filters.issue_type,
            university_id=filters.university_id,
            repository_id=filters.repository_id,
            journal_id=filters.journal_id,
            year=filters.year,
            is_deleted=filters.is_deleted,
            is_current=filters.is_current,
            sort_by=filters.sort_by,
            sort_order=filters.sort_order,
        )
        return await self.reports.paginate(low_quality_filters, limit=limit, offset=offset)

    async def issues(
        self,
        filters: QualityReportFilters | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[QualityIssue]:
        """Return flattened report issues with pagination."""

        reports = await self.reports.list(filters or QualityReportFilters(), limit=500, offset=0)
        items: list[QualityIssue] = []
        issue_filter = filters.issue_type if filters else None
        for report in reports:
            items.extend(_issues_for_report(report, issue_filter=issue_filter))
        total = len(items)
        bounded = Pagination(limit=limit, offset=offset).normalized()
        return Page(
            items=items[bounded.offset : bounded.offset + bounded.limit],
            total=total,
            limit=bounded.limit,
            offset=bounded.offset,
        )

    async def summary(self, filters: QualityReportFilters | None = None) -> QualitySummary:
        """Return aggregate quality scores and grade distribution."""

        filters = filters or QualityReportFilters()
        statement = self.reports._filtered_statement(filters).order_by(None).subquery()
        aggregate = await self.session.execute(
            select(
                func.count(statement.c.id),
                func.avg(statement.c.final_score),
                func.avg(statement.c.completeness_score),
                func.avg(statement.c.validity_score),
                func.avg(statement.c.consistency_score),
                func.avg(statement.c.uniqueness_score),
                func.avg(statement.c.timeliness_score),
                func.avg(statement.c.accessibility_score),
            )
        )
        row = aggregate.one()
        grade_rows = await self.session.execute(
            select(statement.c.grade, func.count(statement.c.id)).group_by(statement.c.grade)
        )
        publication_rows = await self.session.execute(
            self.reports._filtered_statement(filters)
            .with_only_columns(Publication.is_deleted, func.count(QualityReport.id))
            .order_by(None)
            .group_by(Publication.is_deleted)
        )
        deleted_counts = {bool(is_deleted): int(count) for is_deleted, count in publication_rows}

        return QualitySummary(
            total_reports=int(row[0] or 0),
            assessed_publications=int(row[0] or 0),
            active_publications=deleted_counts.get(False, 0),
            deleted_publications=deleted_counts.get(True, 0),
            average_final_score=_decimal_score(row[1] or 0),
            grade_distribution={grade: int(count) for grade, count in grade_rows},
            dimension_averages={
                "completeness": _decimal_score(row[2] or 0),
                "validity": _decimal_score(row[3] or 0),
                "consistency": _decimal_score(row[4] or 0),
                "uniqueness": _decimal_score(row[5] or 0),
                "timeliness": _decimal_score(row[6] or 0),
                "accessibility": _decimal_score(row[7] or 0),
            },
            generated_at=datetime.now(UTC),
            ruleset_version=RULESET_VERSION,
        )

    async def _load_publication(self, publication_id: UUID) -> Publication | None:
        """Load a publication aggregate needed by the quality rules."""

        result = await self.session.scalars(
            select(Publication)
            .where(Publication.id == publication_id)
            .options(
                selectinload(Publication.authors).selectinload(PublicationAuthor.author),
                selectinload(Publication.keywords).selectinload(PublicationKeyword.keyword),
                selectinload(Publication.journal),
                selectinload(Publication.license_record),
                selectinload(Publication.repository),
            )
            .limit(1)
        )
        return result.first()

    async def _persist_assessment(
        self,
        publication: Publication,
        assessment: QualityAssessment,
    ) -> tuple[QualityReport, bool]:
        """Persist a changed report while keeping historical report rows."""

        latest = await self.reports.latest_for_publication(publication.id)
        if latest is not None and not _report_changed(latest, assessment):
            publication.quality_score = assessment.final_score
            await self.session.flush()
            return latest, False

        await self.reports.mark_previous_not_current(publication.id)
        report = QualityReport(
            publication_id=publication.id,
            score=assessment.final_score,
            completeness_score=assessment.completeness_score,
            validity_score=assessment.validity_score,
            consistency_score=assessment.consistency_score,
            uniqueness_score=assessment.uniqueness_score,
            timeliness_score=assessment.timeliness_score,
            accessibility_score=assessment.accessibility_score,
            final_score=assessment.final_score,
            grade=assessment.grade,
            missing_fields=assessment.missing_fields,
            validation_errors=assessment.validation_errors,
            warnings=assessment.warnings,
            recommendations=assessment.recommendations,
            issue_types=assessment.issue_types,
            is_current=True,
            assessed_at=assessment.assessed_at,
            ruleset_version=assessment.ruleset_version,
            metadata_json=assessment.metadata,
        )
        publication.quality_score = assessment.final_score
        await self.reports.add(report)
        return report, True

    def _score_completeness(
        self,
        publication: Publication,
        authors: Sequence[str],
        collector: _IssueCollector,
    ) -> Decimal:
        checks = [
            _check(bool(_clean_text(publication.title)), "title", collector),
            _check(bool(authors), "authors", collector),
            _check(bool(_clean_text(publication.abstract)), "abstract", collector),
            _check(
                bool(publication.publication_date or publication.publication_year),
                "publication_date",
                collector,
            ),
            _check(bool(publication.repository_identifier), "repository_identifier", collector),
            _check(bool(publication.external_id), "external_id", collector),
            _check(
                bool(publication.source and publication.source_type), "source_provenance", collector
            ),
            _check(bool(publication.raw_record), "raw_metadata", collector),
        ]
        return _score_checks(checks)

    def _score_validity(
        self,
        publication: Publication,
        authors: Sequence[str],
        source_urls: Sequence[str],
        collector: _IssueCollector,
    ) -> Decimal:
        title = _clean_text(publication.title)
        abstract = _clean_text(publication.abstract)
        checks = [
            _title_reasonable(title, collector),
            _abstract_meaningful(abstract, collector),
            _publication_year_valid(publication, collector),
            _doi_valid(publication.doi, collector),
            _orcids_valid(_orcid_values(publication), collector),
            _urls_valid(source_urls, collector),
            _language_valid(publication.language, collector),
            _author_names_valid(authors, collector),
            _license_url_valid(publication, collector),
        ]
        return _score_checks(checks)

    def _score_consistency(
        self,
        publication: Publication,
        keywords: Sequence[str],
        collector: _IssueCollector,
    ) -> Decimal:
        checks = [
            _publication_date_matches_year(publication, collector),
            _publisher_journal_consistent(publication, collector),
            _terms_normalized("keyword", keywords, collector),
            _terms_normalized("subject", publication.subjects or [], collector),
            _pdf_distinct_from_article(publication, collector),
        ]
        return _score_checks(checks)

    def _score_uniqueness(
        self,
        authors: Sequence[str],
        keywords: Sequence[str],
        source_urls: Sequence[str],
        collector: _IssueCollector,
    ) -> Decimal:
        checks = [
            _no_duplicates("author", authors, collector),
            _no_duplicates("keyword", keywords, collector),
            _no_duplicates("url", source_urls, collector),
        ]
        return _score_checks(checks)

    def _score_timeliness(self, publication: Publication, collector: _IssueCollector) -> Decimal:
        checks = [
            _timestamp_not_future("harvested_at", publication.harvested_at, collector),
            _timestamp_not_future(
                "repository_datestamp", publication.repository_datestamp, collector
            ),
            _repository_datestamp_before_harvest(publication, collector),
            _publication_year_not_future(publication, collector),
            _harvest_not_stale(publication, collector),
        ]
        return _score_checks(checks)

    def _score_accessibility(
        self,
        publication: Publication,
        source_urls: Sequence[str],
        collector: _IssueCollector,
    ) -> Decimal:
        checks = [
            _check(bool(publication.article_url), "article_url", collector),
            _urls_valid(source_urls, collector),
            _pdf_distinct_from_article(publication, collector),
            _license_recognized(publication, collector),
            _no_duplicates("url", source_urls, collector),
        ]
        return _score_checks(checks)

    async def _evaluate_url_reachability(
        self,
        urls: Sequence[str],
        collector: _IssueCollector,
    ) -> None:
        """Optionally check URL reachability without making it part of default scoring."""

        if not urls:
            return
        try:
            import httpx
        except ImportError:
            collector.add_warning("url_reachability_unavailable", "httpx is not installed.")
            return
        timeout = httpx.Timeout(self.url_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for url in urls:
                try:
                    response = await client.head(url)
                    if response.status_code == 405:
                        response = await client.get(url)
                    if response.status_code >= 400:
                        collector.add_warning(
                            "url_unreachable",
                            f"URL returned HTTP {response.status_code}: {url}",
                        )
                except httpx.HTTPError as exc:
                    collector.add_warning("url_unreachable", f"URL check failed for {url}: {exc}")


class _IssueCollector:
    """Collect de-duplicated issue details while rules are evaluated."""

    def __init__(self) -> None:
        self.missing_fields: list[str] = []
        self.validation_errors: list[str] = []
        self.warnings: list[str] = []
        self.recommendations: list[str] = []
        self.issue_types: list[str] = []

    def add_missing(self, field_name: str, recommendation: str | None = None) -> None:
        """Record a missing field and optional recommendation."""

        self._append(self.missing_fields, field_name)
        self._append(self.issue_types, f"missing_{field_name}")
        if recommendation:
            self._append(self.recommendations, recommendation)

    def add_error(self, issue_type: str, message: str) -> None:
        """Record a validation error."""

        self._append(self.validation_errors, f"{issue_type}: {message}")
        self._append(self.issue_types, issue_type)

    def add_warning(self, issue_type: str, message: str) -> None:
        """Record a warning."""

        self._append(self.warnings, f"{issue_type}: {message}")
        self._append(self.issue_types, issue_type)

    @staticmethod
    def _append(target: list[str], value: str) -> None:
        if value not in target:
            target.append(value)


def _check(condition: bool, field_name: str, collector: _IssueCollector) -> bool:
    """Record a missing field when a completeness check fails."""

    if condition:
        return True
    collector.add_missing(field_name, f"Provide {field_name.replace('_', ' ')} metadata.")
    return False


def _score_checks(checks: Sequence[bool]) -> Decimal:
    """Convert a list of rule booleans into a 0-100 score."""

    if not checks:
        return Decimal("100.00")
    return _decimal_score((sum(1 for check in checks if check) / len(checks)) * 100)


def _decimal_score(value: Decimal | float | int) -> Decimal:
    """Return a bounded score rounded to two decimals."""

    decimal = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return min(max(decimal, Decimal("0.00")), Decimal("100.00"))


def grade_for_score(score: Decimal) -> str:
    """Return the configured letter grade for a final quality score."""

    if score >= Decimal("90.00"):
        return "A"
    if score >= Decimal("80.00"):
        return "B"
    if score >= Decimal("70.00"):
        return "C"
    if score >= Decimal("60.00"):
        return "D"
    return "F"


def _clean_text(value: str | None) -> str:
    """Normalize whitespace for rule checks."""

    return " ".join((value or "").strip().split())


def _is_placeholder(value: str | None) -> bool:
    """Return true when a value is a known placeholder."""

    return _clean_text(value).casefold() in PLACEHOLDER_TEXT


def _title_reasonable(title: str, collector: _IssueCollector) -> bool:
    if not title:
        return False
    if _is_placeholder(title):
        collector.add_error("placeholder_title", "Title is placeholder text.")
        return False
    if len(title) < 8:
        collector.add_error("short_title", "Title is too short to be descriptive.")
        return False
    if len(title) > 500:
        collector.add_warning("long_title", "Title is unusually long.")
    return True


def _abstract_meaningful(abstract: str, collector: _IssueCollector) -> bool:
    if not abstract:
        return False
    if _is_placeholder(abstract) or len(abstract) < 20:
        collector.add_warning("weak_abstract", "Abstract is missing or not descriptive.")
        return False
    return True


def _publication_year_valid(publication: Publication, collector: _IssueCollector) -> bool:
    year = publication.publication_year
    if year is None and publication.publication_date:
        year = publication.publication_date.year
    if year is None:
        return False
    current_year = datetime.now(UTC).year
    if year < 1800 or year > current_year + 1:
        collector.add_error(
            "invalid_publication_year", f"Publication year is unreasonable: {year}."
        )
        return False
    return True


def _publication_year_not_future(publication: Publication, collector: _IssueCollector) -> bool:
    year = publication.publication_year
    if year is None:
        return False
    current_year = datetime.now(UTC).year
    if year > current_year + 1:
        collector.add_error(
            "future_publication_year", f"Publication year is in the future: {year}."
        )
        return False
    return True


def _doi_valid(doi: str | None, collector: _IssueCollector) -> bool:
    if not doi:
        return True
    if normalize_doi(doi) is None:
        collector.add_error("invalid_doi", f"DOI is invalid: {doi}.")
        return False
    return True


def _orcids_valid(values: Sequence[str], collector: _IssueCollector) -> bool:
    invalid = [value for value in values if value and normalize_orcid(value) is None]
    if invalid:
        collector.add_error("invalid_orcid", f"Invalid ORCID values: {', '.join(invalid)}.")
        return False
    return True


def _urls_valid(values: Sequence[str], collector: _IssueCollector) -> bool:
    invalid = [value for value in values if value and not _is_http_url(value)]
    if invalid:
        collector.add_error("invalid_url", f"Invalid HTTP/HTTPS URLs: {', '.join(invalid)}.")
        return False
    return True


def _language_valid(language: str | None, collector: _IssueCollector) -> bool:
    if not language:
        return True
    if LANGUAGE_RE.match(language.strip()) is None:
        collector.add_error("invalid_language", f"Language code is invalid: {language}.")
        return False
    return True


def _author_names_valid(authors: Sequence[str], collector: _IssueCollector) -> bool:
    invalid = [author for author in authors if not _clean_text(author)]
    if invalid:
        collector.add_error("empty_author_name", "One or more author names are empty.")
        return False
    return True


def _license_url_valid(publication: Publication, collector: _IssueCollector) -> bool:
    license_url = _license_url(publication)
    if not license_url:
        return True
    if not _is_http_url(license_url):
        collector.add_error("invalid_license_url", f"License URL is invalid: {license_url}.")
        return False
    return True


def _publication_date_matches_year(publication: Publication, collector: _IssueCollector) -> bool:
    if not publication.publication_date or not publication.publication_year:
        return True
    if publication.publication_date.year != publication.publication_year:
        collector.add_warning(
            "date_year_mismatch",
            "Publication date year does not match publication_year.",
        )
        return False
    return True


def _publisher_journal_consistent(publication: Publication, collector: _IssueCollector) -> bool:
    publisher = _clean_text(publication.publisher).casefold()
    journal = _clean_text(publication.journal.name if publication.journal else None).casefold()
    publisher_looks_like_journal = "journal" in publisher or "bulletin" in publisher
    journal_looks_like_institution = "university" in journal or "college" in journal
    if publisher and journal and publisher_looks_like_journal and journal_looks_like_institution:
        collector.add_warning(
            "publisher_journal_swapped",
            "Publisher and journal fields appear to be swapped.",
        )
        return False
    return True


def _terms_normalized(kind: str, values: Sequence[str], collector: _IssueCollector) -> bool:
    dirty = [value for value in values if value != _clean_text(value) or not _clean_text(value)]
    if dirty:
        collector.add_warning(f"unnormalized_{kind}s", f"{kind.title()} values need normalization.")
        return False
    return True


def _pdf_distinct_from_article(publication: Publication, collector: _IssueCollector) -> bool:
    if not publication.pdf_url or not publication.article_url:
        return True
    if publication.pdf_url.strip().casefold() == publication.article_url.strip().casefold():
        collector.add_warning(
            "pdf_matches_article_url",
            "PDF URL is not distinguishable from article URL.",
        )
        return False
    return True


def _no_duplicates(kind: str, values: Sequence[str], collector: _IssueCollector) -> bool:
    normalized = [_normalize_identity(value) for value in values if value]
    if len(normalized) != len(set(normalized)):
        collector.add_warning(f"duplicate_{kind}s", f"Duplicate {kind} values were detected.")
        return False
    return True


def _timestamp_not_future(
    field_name: str,
    value: datetime | None,
    collector: _IssueCollector,
) -> bool:
    if value is None:
        return field_name != "harvested_at"
    value_utc = _to_utc(value)
    if value_utc > datetime.now(UTC):
        collector.add_error(f"future_{field_name}", f"{field_name} is in the future.")
        return False
    return True


def _repository_datestamp_before_harvest(
    publication: Publication,
    collector: _IssueCollector,
) -> bool:
    if not publication.repository_datestamp or not publication.harvested_at:
        return True
    if _to_utc(publication.repository_datestamp) > _to_utc(publication.harvested_at):
        collector.add_warning(
            "repository_datestamp_after_harvest",
            "Repository datestamp is later than harvested_at.",
        )
        return False
    return True


def _harvest_not_stale(publication: Publication, collector: _IssueCollector) -> bool:
    if not publication.harvested_at:
        collector.add_missing("harvested_at", "Persist harvested_at for provenance.")
        return False
    age_days = (datetime.now(UTC) - _to_utc(publication.harvested_at)).days
    if age_days > 365:
        collector.add_warning("stale_harvest", "Publication has not been harvested in over a year.")
        return False
    return True


def _license_recognized(publication: Publication, collector: _IssueCollector) -> bool:
    license_text = " ".join(
        value
        for value in [
            publication.license,
            publication.license_record.name if publication.license_record else None,
            publication.license_record.url if publication.license_record else None,
        ]
        if value
    ).casefold()
    if not license_text:
        collector.add_warning("missing_license", "License metadata is missing.")
        return False
    recognized = (
        "creative commons" in license_text
        or "cc by" in license_text
        or "creativecommons.org" in license_text
        or "open access" in license_text
    )
    if not recognized:
        collector.add_warning("unrecognized_license", "License metadata is not recognized.")
    return recognized


def _is_http_url(value: str) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme.lower() in HTTP_SCHEMES and bool(parsed.netloc)


def _license_url(publication: Publication) -> str | None:
    if publication.license_record and publication.license_record.url:
        return publication.license_record.url
    if publication.license and _is_http_url(publication.license):
        return publication.license
    return None


def _authors_for(publication: Publication) -> list[str]:
    authors: list[str] = []
    for join in publication.authors or []:
        if isinstance(join, PublicationAuthor) and isinstance(join.author, Author):
            authors.append(join.author.full_name)
    if authors:
        return authors
    normalized = publication.normalized_record or {}
    raw_authors = normalized.get("authors") or []
    return [str(author) for author in raw_authors if str(author).strip()]


def _keywords_for(publication: Publication) -> list[str]:
    keywords: list[str] = []
    for join in publication.keywords or []:
        if isinstance(join, PublicationKeyword) and join.keyword:
            keywords.append(join.keyword.term)
    if keywords:
        return keywords
    normalized = publication.normalized_record or {}
    raw_keywords = normalized.get("keywords") or []
    return [str(keyword) for keyword in raw_keywords if str(keyword).strip()]


def _source_urls_for(publication: Publication) -> list[str]:
    urls: list[str] = []
    urls.extend(str(url) for url in (publication.source_urls or []) if url)
    if publication.article_url:
        urls.append(publication.article_url)
    if publication.pdf_url:
        urls.append(publication.pdf_url)
    return urls


def _orcid_values(publication: Publication) -> list[str]:
    values: list[str] = []
    for join in publication.authors or []:
        if join.orcid:
            values.append(join.orcid)
        if join.author and join.author.orcid:
            values.append(join.author.orcid)
    normalized = publication.normalized_record or {}
    raw_orcids = normalized.get("orcids") or []
    values.extend(str(orcid) for orcid in raw_orcids if orcid)
    return values


def _normalize_identity(value: str) -> str:
    return " ".join(str(value).casefold().strip().split())


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _report_changed(report: QualityReport, assessment: QualityAssessment) -> bool:
    """Return true when important report fields changed enough to preserve history."""

    return any(
        [
            _decimal_score(report.final_score) != assessment.final_score,
            report.grade != assessment.grade,
            list(report.missing_fields or []) != assessment.missing_fields,
            list(report.validation_errors or []) != assessment.validation_errors,
            list(report.warnings or []) != assessment.warnings,
            list(report.recommendations or []) != assessment.recommendations,
            report.ruleset_version != assessment.ruleset_version,
        ]
    )


def _issues_for_report(
    report: QualityReport,
    *,
    issue_filter: str | None = None,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for category, values in [
        (
            "missing_field",
            [f"missing_{field_name}" for field_name in report.missing_fields or []],
        ),
        ("validation_error", report.validation_errors or []),
        ("warning", report.warnings or []),
        ("recommendation", report.recommendations or []),
    ]:
        for message in values:
            issue_type = _issue_type_from_message(message)
            if issue_filter and issue_filter not in {issue_type, message}:
                continue
            issues.append(
                QualityIssue(
                    publication_id=report.publication_id,
                    report_id=report.id,
                    grade=report.grade,
                    final_score=report.final_score,
                    issue_type=issue_type,
                    category=category,
                    message=message,
                    assessed_at=report.assessed_at,
                )
            )
    return issues


def _issue_type_from_message(message: str) -> str:
    """Derive a stable issue type from a stored message or field name."""

    if ":" in message:
        return re.sub(r"[^a-z0-9_]+", "_", message.split(":", 1)[0].casefold()).strip("_")[:80]
    return re.sub(r"[^a-z0-9_]+", "_", message.casefold()).strip("_")[:80]
