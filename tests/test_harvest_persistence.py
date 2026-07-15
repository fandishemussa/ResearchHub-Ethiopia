"""Tests for the metadata persistence pipeline."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "harvester"))

from researchhub.application.harvest_persistence import (  # noqa: E402
    HarvestPersistenceContext,
    HarvestPersistenceService,
)
from researchhub.infrastructure.persistence.models import (  # noqa: E402
    Author,
    Journal,
    Keyword,
    License,
    Publication,
    PublicationAuthor,
    PublicationKeyword,
    PublicationType,
)
from researchhub_harvester.connectors.base import NormalizedPublication  # noqa: E402


def metadata(
    identifier: str = "oai:test:1",
    *,
    doi: str | None = "10.1234/test",
    title: str = "Soil fertility in Ethiopia",
    year: int | None = 2025,
    first_author: str = "Tesfaye Lemma",
    deleted: bool = False,
) -> NormalizedPublication:
    """Create normalized connector metadata for persistence tests."""

    now = datetime.now(UTC)
    return NormalizedPublication(
        external_id=identifier,
        title=title,
        abstract="A useful abstract",
        authors=[first_author],
        affiliations=["Haramaya University"],
        journal="Haramaya Journal of Agriculture",
        publisher="Haramaya University",
        publication_date=None,
        publication_year=year,
        keywords=["soil", "agriculture"],
        subjects=["soil"],
        language="en",
        doi=doi,
        orcid="0000-0002-1825-0097",
        issn="1234-567X",
        isbn=None,
        license="CC BY 4.0",
        article_url="https://repo.example.edu/items/1",
        pdf_url="https://repo.example.edu/items/1.pdf",
        repository="Haramaya IR",
        repository_identifier=identifier,
        source="haramaya-ir",
        source_type="oai-pmh",
        harvested_at=now,
        updated_at=now,
        quality_score=95.0,
        is_deleted=deleted,
        raw_record={
            "metadata": {
                "type": ["Article"],
                "rights": ["CC BY 4.0"],
                "identifier": ["https://repo.example.edu/items/1"],
            },
            "metadata_quality": {"missing_fields": [], "warnings": []},
        },
    )


class StubPersistenceService(HarvestPersistenceService):
    """Persistence service stub that lets persist_many run without a database."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def persist_one(self, item, context):  # type: ignore[override]
        """Return created for every unique item."""

        self.calls.append(item.external_id)
        return type("Outcome", (), {"action": "created"})()


class FakePublicationRepository:
    """Publication repository fake for identity matching tests."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.by_doi: Publication | None = None
        self.by_source: Publication | None = None
        self.by_title_author: Publication | None = None
        self.candidates: list[Publication] = []

    async def get_by_doi(self, doi: str) -> Publication | None:
        """Return DOI match."""

        self.calls.append("doi")
        return self.by_doi

    async def get_by_source_identifier(self, *, source: str, external_id: str) -> Publication | None:
        """Return source identifier match."""

        self.calls.append("source_external_id")
        return self.by_source

    async def find_by_title_year_first_author(self, **kwargs) -> Publication | None:
        """Return title/year/author match."""

        self.calls.append("title_year_first_author")
        return self.by_title_author

    async def title_similarity_candidates(self, **kwargs) -> list[Publication]:
        """Return title similarity candidates."""

        self.calls.append("title_similarity")
        return self.candidates


class ExistingOnlyRepository:
    """Repository fake returning an existing row and recording add calls."""

    def __init__(self, existing) -> None:
        self.existing = existing
        self.added: list[object] = []

    async def get_by_normalized_name(self, *args, **kwargs):
        """Return existing by normalized identity."""

        return self.existing

    async def get_by_normalized_term(self, *args, **kwargs):
        """Return existing keyword by normalized identity."""

        return self.existing

    async def get_by_orcid(self, *args, **kwargs):
        """Return no ORCID match so name match path is exercised."""

        return None

    async def get_by_issn(self, *args, **kwargs):
        """Return no ISSN match so normalized name path is exercised."""

        return None

    async def add(self, entity):
        """Record unexpected additions."""

        self.added.append(entity)
        return entity


class FakeHistoryRepository:
    """Metadata history fake."""

    def __init__(self) -> None:
        self.added: list[object] = []

    async def add(self, entity):
        """Record history entry."""

        self.added.append(entity)
        return entity


class FakeSession:
    """Session fake for deleted-record tests."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0

    def add(self, entity: object) -> None:
        """Record added entity."""

        self.added.append(entity)

    async def flush(self) -> None:
        """Record flush calls."""

        self.flush_count += 1


class HarvestPersistenceTests(unittest.TestCase):
    """Verify metadata persistence pipeline behavior."""

    def test_result_accounting_and_batch_duplicates(self) -> None:
        """Persist-many counts in-batch duplicates before calling persistence."""

        service = StubPersistenceService()
        context = HarvestPersistenceContext(source="haramaya-ir", source_type="oai-pmh")
        result = asyncio.run(
            service.persist_many(
                [
                    metadata("one", doi="10.1234/dup"),
                    metadata("two", doi="10.1234/dup"),
                    metadata("three", doi="10.1234/unique"),
                ],
                context,
            )
        )

        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(service.calls, ["one", "three"])

    def test_identity_matching_order_prefers_doi(self) -> None:
        """Identity matching follows DOI before weaker identifiers."""

        service = object.__new__(HarvestPersistenceService)
        repo = FakePublicationRepository()
        repo.by_doi = Publication(id=uuid4(), title="Existing", source="s", source_type="oai-pmh")
        service.publications = repo

        found, matched_by = asyncio.run(service._match_existing_publication(metadata()))

        self.assertIs(found, repo.by_doi)
        self.assertEqual(matched_by, "doi")
        self.assertEqual(repo.calls, ["doi"])

    def test_identity_matching_uses_similarity_fallback(self) -> None:
        """Title similarity fallback matches highly similar titles."""

        service = object.__new__(HarvestPersistenceService)
        repo = FakePublicationRepository()
        repo.candidates = [
            Publication(
                id=uuid4(),
                title="Soil fertility in Ethiopia",
                normalized_title="soil fertility in ethiopia",
                source="s",
                source_type="oai-pmh",
                publication_year=2025,
            )
        ]
        service.publications = repo

        found, matched_by = asyncio.run(
            service._match_existing_publication(
                metadata(doi=None, title="Soil fertility in Ethiopia", first_author="Another Author")
            )
        )

        self.assertIs(found, repo.candidates[0])
        self.assertEqual(matched_by, "title_similarity")
        self.assertEqual(
            repo.calls,
            ["source_external_id", "title_year_first_author", "title_similarity"],
        )

    def test_controlled_values_are_not_duplicated(self) -> None:
        """Existing authors, journals, keywords, types, and licenses are reused."""

        service = object.__new__(HarvestPersistenceService)
        existing_author = Author(id=uuid4(), full_name="Tesfaye Lemma", normalized_name="tesfaye lemma")
        existing_journal = Journal(id=uuid4(), name="Journal", normalized_name="journal")
        existing_keyword = Keyword(id=uuid4(), term="soil", normalized_term="soil")
        existing_type = PublicationType(id=uuid4(), name="Article", normalized_name="article")
        existing_license = License(id=uuid4(), name="CC BY 4.0", normalized_name="cc by 40")
        service.authors = ExistingOnlyRepository(existing_author)
        service.journals = ExistingOnlyRepository(existing_journal)
        service.keywords = ExistingOnlyRepository(existing_keyword)
        service.publication_types = ExistingOnlyRepository(existing_type)
        service.licenses = ExistingOnlyRepository(existing_license)

        item = metadata()
        university = type("University", (), {"id": uuid4()})()

        resolved_author = asyncio.run(service._resolve_author("Tesfaye Lemma", None))
        resolved_journal = asyncio.run(service._resolve_journal(item, university))
        resolved_keyword = asyncio.run(service._resolve_keyword("soil"))
        resolved_type = asyncio.run(service._resolve_publication_type(item))
        resolved_license = asyncio.run(service._resolve_license(item))

        self.assertIs(resolved_author, existing_author)
        self.assertIs(resolved_journal, existing_journal)
        self.assertIs(resolved_keyword, existing_keyword)
        self.assertIs(resolved_type, existing_type)
        self.assertIs(resolved_license, existing_license)
        self.assertEqual(service.authors.added, [])
        self.assertEqual(service.journals.added, [])
        self.assertEqual(service.keywords.added, [])
        self.assertEqual(service.publication_types.added, [])
        self.assertEqual(service.licenses.added, [])

    def test_deleted_record_marks_existing_and_writes_history(self) -> None:
        """Deleted OAI records mark existing rows and preserve history."""

        service = object.__new__(HarvestPersistenceService)
        service.session = FakeSession()
        service.history = FakeHistoryRepository()
        existing = Publication(
            id=uuid4(),
            title="Existing",
            source="haramaya-ir",
            source_type="oai-pmh",
            is_deleted=False,
        )

        outcome = asyncio.run(
            service._persist_deleted_record(existing, metadata(deleted=True), "doi")
        )

        self.assertEqual(outcome.action, "deleted")
        self.assertTrue(existing.is_deleted)
        self.assertEqual(len(service.history.added), 1)
        self.assertEqual(service.history.added[0].field_name, "is_deleted")

    def test_duplicate_authors_and_keywords_create_one_pending_association(self) -> None:
        """Repeated normalized metadata must not violate association constraints."""

        service = object.__new__(HarvestPersistenceService)
        service.session = FakeSession()
        author = Author(id=uuid4(), full_name="Tesfaye Lemma", normalized_name="tesfaye lemma")
        keyword = Keyword(id=uuid4(), term="soil", normalized_term="soil")

        async def no_authors(_publication_id):
            return set()

        async def no_keywords(_publication_id):
            return set()

        async def resolve_author(_name, _orcid):
            return author

        async def resolve_keyword(_term):
            return keyword

        service._existing_author_ids = no_authors
        service._existing_keyword_ids = no_keywords
        service._resolve_author = resolve_author
        service._resolve_keyword = resolve_keyword
        item = metadata()
        item.authors = ["Tesfaye Lemma", "Tesfaye Lemma", "TESFAYE LEMMA"]
        item.affiliations = ["Haramaya University"] * 3
        item.keywords = ["soil", "Soil", "soil"]
        publication = Publication(
            id=uuid4(), title=item.title, source=item.source, source_type=item.source_type
        )

        asyncio.run(service._sync_authors(publication, item))
        asyncio.run(service._sync_keywords(publication, item))

        author_links = [row for row in service.session.added if isinstance(row, PublicationAuthor)]
        keyword_links = [row for row in service.session.added if isinstance(row, PublicationKeyword)]
        self.assertEqual(len(author_links), 1)
        self.assertEqual(len(keyword_links), 1)

    def test_pipeline_migration_contains_required_tables_and_columns(self) -> None:
        """The Alembic migration adds controlled vocabulary and provenance columns."""

        migration = (
            ROOT
            / "backend"
            / "alembic"
            / "versions"
            / "0003_metadata_persistence_pipeline.py"
        ).read_text(encoding="utf-8")

        self.assertIn("publication_types", migration)
        self.assertIn("licenses", migration)
        self.assertIn("normalized_title", migration)
        self.assertIn("repository_datestamp", migration)
        self.assertIn("normalized_record", migration)


if __name__ == "__main__":
    unittest.main()
