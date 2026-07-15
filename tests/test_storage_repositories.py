"""Tests for SQLAlchemy repository pattern storage layer."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from researchhub.infrastructure.persistence.models import University  # noqa: E402
from researchhub.infrastructure.persistence.repositories import (  # noqa: E402
    HarvestJobFilters,
    HarvestJobRepository,
    InstitutionalRepositoryRepository,
    Pagination,
    PublicationFilters,
    PublicationRepository,
    RepositoryFilters,
    UniversityFilters,
    UniversityRepository,
)
from sqlalchemy.dialects import postgresql  # noqa: E402


def compile_postgres(statement: object) -> str:
    """Compile a SQLAlchemy statement using the PostgreSQL dialect."""

    return str(statement.compile(dialect=postgresql.dialect()))


class FakeAsyncSession:
    """Minimal async session fake for repository CRUD behavior."""

    def __init__(self) -> None:
        self.entities: dict[tuple[type[object], object], object] = {}
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.flush_count = 0

    def add(self, entity: object) -> None:
        """Record and store an added entity."""

        self.added.append(entity)
        self.entities[(type(entity), entity.id)] = entity

    async def get(self, model: type[object], entity_id: object) -> object | None:
        """Return a stored entity by model and id."""

        return self.entities.get((model, entity_id))

    async def flush(self) -> None:
        """Record a flush call."""

        self.flush_count += 1

    async def delete(self, entity: object) -> None:
        """Record a deleted entity."""

        self.deleted.append(entity)


class RepositoryQueryTests(unittest.TestCase):
    """Verify repository filters generate expected PostgreSQL SQL."""

    def test_university_filters_and_pagination(self) -> None:
        """University filters include search, country, active flag, limit, and offset."""

        statement = UniversityRepository(None).query(
            UniversityFilters(q="haramaya", country="Ethiopia", is_active=True),
            Pagination(limit=999, offset=-10),
        )
        sql = compile_postgres(statement)

        self.assertIn("FROM universities", sql)
        self.assertIn("universities.country", sql)
        self.assertIn("universities.is_active IS true", sql)
        self.assertEqual(statement._limit_clause.value, 500)
        self.assertEqual(statement._offset_clause.value, 0)

    def test_repository_filters(self) -> None:
        """Institutional repository filters include university, platform, and status."""

        university_id = uuid4()
        statement = InstitutionalRepositoryRepository(None).query(
            RepositoryFilters(
                university_id=university_id,
                platform="DSpace",
                q="repository",
                is_active=True,
            )
        )
        sql = compile_postgres(statement)

        self.assertIn("FROM repositories", sql)
        self.assertIn("repositories.university_id", sql)
        self.assertIn("repositories.platform", sql)
        self.assertIn("repositories.is_active IS true", sql)

    def test_publication_filters_join_authors_and_keywords(self) -> None:
        """Publication filters can combine author and keyword joins safely."""

        statement = PublicationRepository(None).query(
            PublicationFilters(
                q="soil",
                author="Tesfaye Lemma",
                keyword="Agriculture",
                year_from=2020,
                year_to=2026,
                language="en",
                is_deleted=False,
            )
        )
        sql = compile_postgres(statement)

        self.assertIn("JOIN publication_authors", sql)
        self.assertIn("JOIN authors", sql)
        self.assertIn("JOIN publication_keywords", sql)
        self.assertIn("JOIN keywords", sql)
        self.assertIn("publications.publication_year >=", sql)
        self.assertIn("publications.publication_year <=", sql)
        self.assertIn("publications.is_deleted IS false", sql)

    def test_harvest_job_filters(self) -> None:
        """Harvest job filters support connector, status, year, and errors."""

        statement = HarvestJobRepository(None).query(
            HarvestJobFilters(
                connector_id=uuid4(),
                status="running",
                since_year=2026,
                has_errors=True,
            )
        )
        sql = compile_postgres(statement)

        self.assertIn("FROM harvest_jobs", sql)
        self.assertIn("harvest_jobs.connector_id", sql)
        self.assertIn("harvest_jobs.status", sql)
        self.assertIn("EXTRACT(year FROM harvest_jobs.since)", sql)
        self.assertIn("harvest_jobs.error_count > ", sql)


class RepositoryCrudTests(unittest.TestCase):
    """Verify generic CRUD behavior without a live database."""

    def test_add_update_soft_delete_and_hard_delete(self) -> None:
        """Generic repository CRUD uses session add/get/delete/flush correctly."""

        async def run() -> None:
            session = FakeAsyncSession()
            repository = UniversityRepository(session)
            entity_id = uuid4()
            university = University(
                id=entity_id,
                code="HU",
                name="Haramaya University",
                country="Ethiopia",
                city="Haramaya",
            )

            added = await repository.add(university)
            self.assertIs(added, university)
            self.assertEqual(session.flush_count, 1)

            updated = await repository.update(entity_id, {"name": "Updated HU"})
            self.assertEqual(updated.name, "Updated HU")
            self.assertEqual(session.flush_count, 2)

            soft_deleted = await repository.delete(entity_id)
            self.assertTrue(soft_deleted)
            self.assertFalse(university.is_active)
            self.assertEqual(session.flush_count, 3)

            hard_deleted = await repository.delete(entity_id, hard=True)
            self.assertTrue(hard_deleted)
            self.assertIn(university, session.deleted)
            self.assertEqual(session.flush_count, 4)

        asyncio.run(run())


class AlembicMigrationTests(unittest.TestCase):
    """Verify storage-layer migration is present."""

    def test_storage_layer_indexes_migration_exists(self) -> None:
        """The storage layer migration contains expected composite indexes."""

        migration = (
            ROOT
            / "backend"
            / "alembic"
            / "versions"
            / "0002_storage_layer_indexes.py"
        ).read_text(encoding="utf-8")

        self.assertIn("0002_storage_layer_indexes", migration)
        self.assertIn("ix_publications_repo_year_lang_deleted", migration)
        self.assertIn("ix_harvest_jobs_connector_status_started", migration)


if __name__ == "__main__":
    unittest.main()

