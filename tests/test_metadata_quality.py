"""Tests for the Phase 1 metadata quality assessment engine."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from researchhub.application.metadata_quality import (  # noqa: E402
    MetadataQualityService,
    MetadataQualityWeights,
    grade_for_score,
)
from researchhub.infrastructure.persistence.models import (  # noqa: E402
    Author,
    Journal,
    Keyword,
    License,
    Publication,
    PublicationAuthor,
    PublicationKeyword,
    QualityReport,
)
from researchhub.infrastructure.persistence.repositories import (  # noqa: E402
    Pagination,
    QualityReportFilters,
    QualityReportRepository,
)
from sqlalchemy.dialects import postgresql  # noqa: E402


def compile_postgres(statement: object) -> str:
    """Compile a SQLAlchemy statement using the PostgreSQL dialect."""

    return str(statement.compile(dialect=postgresql.dialect()))


class FakeSession:
    """Minimal fake session for unit-level persistence tests."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0

    def add(self, entity: object) -> None:
        """Record added entities."""

        self.added.append(entity)

    async def flush(self) -> None:
        """Record flushes."""

        self.flush_count += 1


class FakeQualityReportRepository:
    """Quality report repository fake for history preservation tests."""

    def __init__(self, latest: QualityReport | None = None) -> None:
        self.latest = latest
        self.marked_previous = 0
        self.added: list[QualityReport] = []

    async def latest_for_publication(self, publication_id):
        """Return the configured latest report."""

        return self.latest

    async def mark_previous_not_current(self, publication_id):
        """Record history rollover."""

        self.marked_previous += 1
        if self.latest:
            self.latest.is_current = False
        return self.marked_previous

    async def add(self, report):
        """Record the new report."""

        self.added.append(report)
        return report


def complete_publication() -> Publication:
    """Create a rich in-memory publication aggregate."""

    publication = Publication(
        id=uuid4(),
        external_id="oai:eajhbs:1",
        title="Maternal health service utilization in eastern Ethiopia",
        abstract="This study evaluates health service utilization using repository metadata.",
        normalized_title="maternal health service utilization in eastern ethiopia",
        publisher="Haramaya University",
        publication_date=date(2025, 3, 1),
        publication_year=2025,
        subjects=["Public health"],
        language="en",
        doi="10.1234/eajhbs.2025.1",
        article_url="https://eajhbs.haramaya.edu.et/article/view/1",
        pdf_url="https://eajhbs.haramaya.edu.et/article/download/1/1",
        source_urls=["https://eajhbs.haramaya.edu.et/article/view/1"],
        repository_identifier="oai:eajhbs:1",
        repository_datestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source="haramaya-eajhbs",
        source_type="oai-pmh",
        harvested_at=datetime.now(UTC),
        is_deleted=False,
        raw_record={"header": {"identifier": "oai:eajhbs:1"}},
        normalized_record={"authors": ["Aster Bekele"], "keywords": ["maternal health"]},
    )
    author = Author(
        id=uuid4(),
        full_name="Aster Bekele",
        normalized_name="aster bekele",
        orcid="0000-0002-1825-0097",
    )
    keyword = Keyword(id=uuid4(), term="maternal health", normalized_term="maternal health")
    publication.authors = [
        PublicationAuthor(
            id=uuid4(),
            author=author,
            author_order=1,
            orcid="0000-0002-1825-0097",
        )
    ]
    publication.keywords = [PublicationKeyword(id=uuid4(), keyword=keyword)]
    publication.journal = Journal(
        id=uuid4(),
        name="East African Journal of Health and Biomedical Sciences",
        normalized_name="east african journal of health and biomedical sciences",
    )
    publication.license_record = License(
        id=uuid4(),
        name="CC BY 4.0",
        normalized_name="cc by 40",
        url="https://creativecommons.org/licenses/by/4.0/",
    )
    return publication


class MetadataQualityTests(unittest.TestCase):
    """Verify quality scoring and report persistence behavior."""

    def test_complete_publication_receives_a_grade(self) -> None:
        """Rich metadata scores highly across all dimensions."""

        service = MetadataQualityService(FakeSession())
        assessment = asyncio.run(service.assess_publication(complete_publication()))

        self.assertEqual(assessment.grade, "A")
        self.assertGreaterEqual(assessment.final_score, 90)
        self.assertEqual(assessment.missing_fields, [])
        self.assertNotIn("invalid_doi", assessment.issue_types)

    def test_low_quality_publication_collects_missing_and_invalid_issues(self) -> None:
        """Incomplete placeholder metadata receives actionable issue details."""

        publication = Publication(
            id=uuid4(),
            external_id=None,
            title="N/A",
            abstract="abstract",
            publication_year=3020,
            language="english",
            doi="bad-doi",
            article_url="ftp://example.invalid/item",
            pdf_url="ftp://example.invalid/item",
            source="haramaya-eajhbs",
            source_type="oai-pmh",
            harvested_at=None,
            raw_record={},
            is_deleted=False,
        )
        publication.authors = []
        publication.keywords = [
            PublicationKeyword(
                id=uuid4(),
                keyword=Keyword(id=uuid4(), term="  Health  ", normalized_term="health"),
            ),
            PublicationKeyword(
                id=uuid4(),
                keyword=Keyword(id=uuid4(), term="Health", normalized_term="health"),
            ),
        ]

        service = MetadataQualityService(FakeSession())
        assessment = asyncio.run(service.assess_publication(publication))

        self.assertEqual(assessment.grade, "F")
        self.assertIn("authors", assessment.missing_fields)
        self.assertIn("external_id", assessment.missing_fields)
        self.assertIn("invalid_doi", assessment.issue_types)
        self.assertIn("invalid_url", assessment.issue_types)
        self.assertIn("duplicate_keywords", assessment.issue_types)

    def test_weights_are_configurable_and_normalized(self) -> None:
        """Custom weights are normalized before final score calculation."""

        weights = MetadataQualityWeights.from_mapping(
            {
                "completeness": 10,
                "validity": 0,
                "consistency": 0,
                "uniqueness": 0,
                "timeliness": 0,
                "accessibility": 0,
            }
        )

        self.assertEqual(weights.completeness, 1.0)
        self.assertEqual(sum(weights.as_dict().values()), 1.0)
        self.assertEqual(grade_for_score(95), "A")
        self.assertEqual(grade_for_score(59), "F")

    def test_changed_assessment_creates_history_and_updates_publication_score(self) -> None:
        """A changed score marks the old report historical and creates a new current row."""

        publication = complete_publication()
        existing = QualityReport(
            id=uuid4(),
            publication_id=publication.id,
            score=10,
            final_score=10,
            grade="F",
            missing_fields=["title"],
            validation_errors=[],
            warnings=[],
            recommendations=[],
            issue_types=["missing_title"],
            is_current=True,
            assessed_at=datetime.now(UTC),
            ruleset_version="metadata-quality-v1",
        )
        service = MetadataQualityService(FakeSession())
        service.reports = FakeQualityReportRepository(existing)
        assessment = asyncio.run(service.assess_publication(publication))

        report, created = asyncio.run(service._persist_assessment(publication, assessment))

        self.assertTrue(created)
        self.assertFalse(existing.is_current)
        self.assertTrue(report.is_current)
        self.assertEqual(publication.quality_score, assessment.final_score)
        self.assertEqual(len(service.reports.added), 1)

    def test_unchanged_assessment_reuses_current_report(self) -> None:
        """An unchanged report is reused instead of duplicating history rows."""

        publication = complete_publication()
        service = MetadataQualityService(FakeSession())
        assessment = asyncio.run(service.assess_publication(publication))
        existing = QualityReport(
            id=uuid4(),
            publication_id=publication.id,
            score=assessment.final_score,
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
        )
        service.reports = FakeQualityReportRepository(existing)

        report, created = asyncio.run(service._persist_assessment(publication, assessment))

        self.assertFalse(created)
        self.assertIs(report, existing)
        self.assertEqual(service.reports.added, [])


class QualityRepositoryTests(unittest.TestCase):
    """Verify quality report filters compile to expected PostgreSQL SQL."""

    def test_quality_filters_include_jsonb_issue_and_institution_joins(self) -> None:
        """Quality filters support issue type, scope filters, sorting, and pagination."""

        statement = QualityReportRepository(None).query(
            QualityReportFilters(
                grade="F",
                max_score=60,
                issue_type="invalid_doi",
                university_id=uuid4(),
                repository_id=uuid4(),
                journal_id=uuid4(),
                year=2025,
                is_deleted=False,
                sort_by="final_score",
                sort_order="asc",
            ),
            Pagination(limit=25, offset=5),
        )
        sql = compile_postgres(statement)

        self.assertIn("FROM quality_reports", sql)
        self.assertIn("JOIN publications", sql)
        self.assertIn("JOIN repositories", sql)
        self.assertIn("quality_reports.issue_types", sql)
        self.assertIn("quality_reports.final_score <=", sql)
        self.assertIn("publications.is_deleted IS false", sql)
        self.assertEqual(statement._limit_clause.value, 25)
        self.assertEqual(statement._offset_clause.value, 5)

    def test_quality_migration_expands_report_schema(self) -> None:
        """The migration contains dimension scores, grade, issues, and history columns."""

        migration = (
            ROOT / "backend" / "alembic" / "versions" / "0004_metadata_quality_assessment.py"
        ).read_text(encoding="utf-8")

        self.assertIn("completeness_score", migration)
        self.assertIn("validation_errors", migration)
        self.assertIn("issue_types", migration)
        self.assertIn("is_current", migration)
        self.assertIn("ix_quality_reports_grade_score", migration)


if __name__ == "__main__":
    unittest.main()
