"""Repository Pattern implementations for ResearchHub persistence.

Repositories keep SQLAlchemy query construction and persistence mechanics out of
application services. Each repository exposes CRUD operations, pagination, and
entity-specific filtering while sharing a small generic base class.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast
from uuid import UUID

from sqlalchemy import Select, desc, func, or_, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import InstrumentedAttribute

from researchhub.infrastructure.persistence.base import Base
from researchhub.infrastructure.persistence.models import (
    Author,
    HarvestJob,
    Journal,
    Keyword,
    License,
    MetadataHistory,
    Publication,
    PublicationAuthor,
    PublicationKeyword,
    PublicationType,
    QualityReport,
    University,
)
from researchhub.infrastructure.persistence.models import (
    Repository as RepositoryModel,
)

ModelT = TypeVar("ModelT", bound=Base)
PageItemT = TypeVar("PageItemT")


@dataclass(frozen=True, slots=True)
class Pagination:
    """Limit/offset pagination request with defensive bounds."""

    limit: int = 50
    offset: int = 0

    def normalized(self) -> Pagination:
        """Return a bounded pagination object safe for database queries."""

        return Pagination(limit=min(max(self.limit, 1), 500), offset=max(self.offset, 0))


@dataclass(frozen=True, slots=True)
class Page(Generic[PageItemT]):
    """Paginated repository result."""

    items: Sequence[PageItemT]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class UniversityFilters:
    """Filters for university catalog queries."""

    q: str | None = None
    country: str | None = None
    city: str | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class RepositoryFilters:
    """Filters for institutional repository/source queries."""

    university_id: UUID | None = None
    platform: str | None = None
    q: str | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class PublicationFilters:
    """Filters for normalized publication queries."""

    repository_id: UUID | None = None
    source: str | None = None
    source_type: str | None = None
    q: str | None = None
    author: str | None = None
    keyword: str | None = None
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    language: str | None = None
    doi: str | None = None
    is_deleted: bool | None = None


@dataclass(frozen=True, slots=True)
class AuthorFilters:
    """Filters for author queries."""

    q: str | None = None
    orcid: str | None = None
    university_id: UUID | None = None
    department_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class KeywordFilters:
    """Filters for keyword queries."""

    q: str | None = None
    vocabulary: str | None = None


@dataclass(frozen=True, slots=True)
class JournalFilters:
    """Filters for journal queries."""

    q: str | None = None
    issn: str | None = None
    university_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class HarvestJobFilters:
    """Filters for harvest job operational queries."""

    connector_id: UUID | None = None
    status: str | None = None
    since_year: int | None = None
    has_errors: bool | None = None


@dataclass(frozen=True, slots=True)
class QualityReportFilters:
    """Filters for metadata quality reports and issue views."""

    publication_id: UUID | None = None
    grade: str | None = None
    min_score: float | None = None
    max_score: float | None = None
    issue_type: str | None = None
    university_id: UUID | None = None
    repository_id: UUID | None = None
    journal_id: UUID | None = None
    year: int | None = None
    is_deleted: bool | None = None
    is_current: bool | None = True
    sort_by: str = "assessed_at"
    sort_order: str = "desc"


class AsyncRepository(Generic[ModelT]):
    """Generic async repository implementing common CRUD behavior."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, model: type[ModelT] | None = None) -> None:
        self.session = session
        if model is not None:
            self.model = model

    async def get(self, entity_id: UUID) -> ModelT | None:
        """Return an entity by UUID or ``None``."""

        return await self.session.get(self.model, entity_id)

    async def add(self, entity: ModelT) -> ModelT:
        """Persist an entity and flush so generated identifiers are available."""

        self.session.add(entity)
        await self.session.flush()
        return entity

    async def create(self, values: Mapping[str, Any]) -> ModelT:
        """Create and persist an entity from mapped values."""

        entity = self.model(**dict(values))
        return await self.add(entity)

    async def update(self, entity_id: UUID, values: Mapping[str, Any]) -> ModelT | None:
        """Update an entity in-place and return it, or ``None`` when missing."""

        entity = await self.get(entity_id)
        if entity is None:
            return None
        for field, value in values.items():
            if value is not None and hasattr(entity, field):
                setattr(entity, field, value)
        await self.session.flush()
        return entity

    async def delete(self, entity_id: UUID, *, hard: bool = False) -> bool:
        """Delete an entity.

        Soft-delete is used when the model has an ``is_active`` or ``is_deleted``
        flag. Set ``hard=True`` to issue a physical delete.
        """

        entity = await self.get(entity_id)
        if entity is None:
            return False
        if not hard and hasattr(entity, "is_active"):
            entity.is_active = False
        elif not hard and hasattr(entity, "is_deleted"):
            entity.is_deleted = True
        else:
            await self.session.delete(entity)
        await self.session.flush()
        return True

    async def delete_where(self, *criteria: Any) -> int:
        """Physically delete rows matching criteria and return affected count."""

        result = cast(
            CursorResult[Any],
            await self.session.execute(sa_delete(self.model).where(*criteria)),
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    def query(
        self, filters: Any = None, pagination: Pagination | None = None
    ) -> Select[tuple[ModelT]]:
        """Build a filtered, ordered, paginated SELECT statement."""

        statement = self._filtered_statement(filters)
        statement = self._ordered_statement(statement)
        if pagination:
            page = pagination.normalized()
            statement = statement.limit(page.limit).offset(page.offset)
        return statement

    async def list(
        self,
        filters: Any = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ModelT]:
        """Return filtered rows using limit/offset pagination."""

        statement = self.query(filters, Pagination(limit=limit, offset=offset))
        result = await self.session.scalars(statement)
        return result.unique().all()

    async def paginate(
        self,
        filters: Any = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[ModelT]:
        """Return filtered rows plus total count."""

        page = Pagination(limit=limit, offset=offset).normalized()
        items = await self.list(filters, limit=page.limit, offset=page.offset)
        total = await self.count(filters)
        return Page(items=items, total=total, limit=page.limit, offset=page.offset)

    async def count(self, filters: Any = None) -> int:
        """Return the number of rows matching filters."""

        statement = self._filtered_statement(filters).order_by(None).limit(None).offset(None)
        count_statement = select(func.count()).select_from(statement.subquery())
        total = await self.session.scalar(count_statement)
        return int(total or 0)

    def _filtered_statement(self, filters: Any = None) -> Select[tuple[ModelT]]:
        """Apply entity-specific filters to a base select."""

        return select(self.model)

    def _ordered_statement(self, statement: Select[tuple[ModelT]]) -> Select[tuple[ModelT]]:
        """Apply default ordering."""

        updated_at = getattr(self.model, "updated_at", None)
        if updated_at is not None:
            return statement.order_by(desc(updated_at))
        created_at = getattr(self.model, "created_at", None)
        if created_at is not None:
            return statement.order_by(desc(created_at))
        return statement


class UniversityRepository(AsyncRepository[University]):
    """Repository for university CRUD and filtering."""

    model = University

    async def get_by_code(self, code: str) -> University | None:
        """Return a university by normalized code."""

        result = await self.session.scalars(
            select(University).where(University.code == code.upper()).limit(1)
        )
        return result.first()

    def _filtered_statement(
        self, filters: UniversityFilters | None = None
    ) -> Select[tuple[University]]:
        statement = select(University)
        if filters is None:
            return statement
        if filters.q:
            q = f"%{filters.q}%"
            statement = statement.where(or_(University.name.ilike(q), University.code.ilike(q)))
        if filters.country:
            statement = statement.where(University.country == filters.country)
        if filters.city:
            statement = statement.where(University.city.ilike(f"%{filters.city}%"))
        if filters.is_active is not None:
            statement = statement.where(University.is_active.is_(filters.is_active))
        return statement


class InstitutionalRepositoryRepository(AsyncRepository[RepositoryModel]):
    """Repository for institutional repositories, DSpace, and OJS sources."""

    model = RepositoryModel

    def _filtered_statement(
        self, filters: RepositoryFilters | None = None
    ) -> Select[tuple[RepositoryModel]]:
        statement = select(RepositoryModel)
        if filters is None:
            return statement
        if filters.university_id:
            statement = statement.where(RepositoryModel.university_id == filters.university_id)
        if filters.platform:
            statement = statement.where(RepositoryModel.platform == filters.platform)
        if filters.q:
            q = f"%{filters.q}%"
            statement = statement.where(
                or_(RepositoryModel.name.ilike(q), RepositoryModel.base_url.ilike(q))
            )
        if filters.is_active is not None:
            statement = statement.where(RepositoryModel.is_active.is_(filters.is_active))
        return statement


class AuthorRepository(AsyncRepository[Author]):
    """Repository for author CRUD and lookup."""

    model = Author

    async def get_by_orcid(self, orcid: str) -> Author | None:
        """Return an author by ORCID."""

        result = await self.session.scalars(select(Author).where(Author.orcid == orcid).limit(1))
        return result.first()

    async def get_by_normalized_name(self, normalized_name: str) -> Author | None:
        """Return an author by normalized display name."""

        result = await self.session.scalars(
            select(Author).where(Author.normalized_name == normalized_name).limit(1)
        )
        return result.first()

    def _filtered_statement(self, filters: AuthorFilters | None = None) -> Select[tuple[Author]]:
        statement = select(Author)
        if filters is None:
            return statement
        if filters.q:
            q = f"%{filters.q}%"
            statement = statement.where(
                or_(Author.full_name.ilike(q), Author.normalized_name.ilike(q))
            )
        if filters.orcid:
            statement = statement.where(Author.orcid == filters.orcid)
        if filters.university_id:
            statement = statement.where(Author.university_id == filters.university_id)
        if filters.department_id:
            statement = statement.where(Author.department_id == filters.department_id)
        return statement


class KeywordRepository(AsyncRepository[Keyword]):
    """Repository for keyword CRUD and lookup."""

    model = Keyword

    async def get_by_normalized_term(self, normalized_term: str) -> Keyword | None:
        """Return a keyword by normalized term."""

        result = await self.session.scalars(
            select(Keyword).where(Keyword.normalized_term == normalized_term).limit(1)
        )
        return result.first()

    def _filtered_statement(self, filters: KeywordFilters | None = None) -> Select[tuple[Keyword]]:
        statement = select(Keyword)
        if filters is None:
            return statement
        if filters.q:
            q = f"%{filters.q}%"
            statement = statement.where(
                or_(Keyword.term.ilike(q), Keyword.normalized_term.ilike(q))
            )
        if filters.vocabulary:
            statement = statement.where(Keyword.vocabulary == filters.vocabulary)
        return statement


class JournalRepository(AsyncRepository[Journal]):
    """Repository for journal CRUD and lookup."""

    model = Journal

    async def get_by_normalized_name(
        self, normalized_name: str, university_id: UUID | None = None
    ) -> Journal | None:
        """Return a journal by normalized name and optional university."""

        statement = select(Journal).where(Journal.normalized_name == normalized_name)
        if university_id:
            statement = statement.where(Journal.university_id == university_id)
        result = await self.session.scalars(statement.limit(1))
        return result.first()

    async def get_by_issn(self, issn: str) -> Journal | None:
        """Return a journal by print or electronic ISSN."""

        result = await self.session.scalars(
            select(Journal).where(or_(Journal.issn == issn, Journal.eissn == issn)).limit(1)
        )
        return result.first()

    def _filtered_statement(self, filters: JournalFilters | None = None) -> Select[tuple[Journal]]:
        statement = select(Journal)
        if filters is None:
            return statement
        if filters.q:
            q = f"%{filters.q}%"
            statement = statement.where(
                or_(Journal.name.ilike(q), Journal.normalized_name.ilike(q))
            )
        if filters.issn:
            statement = statement.where(
                or_(Journal.issn == filters.issn, Journal.eissn == filters.issn)
            )
        if filters.university_id:
            statement = statement.where(Journal.university_id == filters.university_id)
        return statement


class PublicationTypeRepository(AsyncRepository[PublicationType]):
    """Repository for publication type vocabulary."""

    model = PublicationType

    async def get_by_normalized_name(self, normalized_name: str) -> PublicationType | None:
        """Return a publication type by normalized name."""

        result = await self.session.scalars(
            select(PublicationType)
            .where(PublicationType.normalized_name == normalized_name)
            .limit(1)
        )
        return result.first()


class LicenseRepository(AsyncRepository[License]):
    """Repository for license vocabulary."""

    model = License

    async def get_by_normalized_name(self, normalized_name: str) -> License | None:
        """Return a license by normalized name."""

        result = await self.session.scalars(
            select(License).where(License.normalized_name == normalized_name).limit(1)
        )
        return result.first()


class MetadataHistoryRepository(AsyncRepository[MetadataHistory]):
    """Repository for metadata provenance history."""

    model = MetadataHistory


class PublicationRepository(AsyncRepository[Publication]):
    """Repository for publication CRUD, filtering, and duplicate lookups."""

    model = Publication

    @staticmethod
    def with_relations(statement: Select[tuple[Publication]]) -> Select[tuple[Publication]]:
        """Eager-load public author and keyword data without N+1 queries."""

        return statement.options(
            selectinload(Publication.authors).selectinload(PublicationAuthor.author),
            selectinload(Publication.keywords).selectinload(PublicationKeyword.keyword),
        )

    async def get(self, entity_id: UUID) -> Publication | None:
        """Return one publication with its public relationships loaded."""

        result = await self.session.scalars(
            self.with_relations(select(Publication).where(Publication.id == entity_id).limit(1))
        )
        return result.first()

    async def get_by_doi(self, doi: str) -> Publication | None:
        """Return a publication by DOI."""

        result = await self.session.scalars(
            select(Publication).where(Publication.doi == doi).limit(1)
        )
        return result.first()

    async def get_by_source_identifier(
        self, *, source: str, external_id: str
    ) -> Publication | None:
        """Return a publication by connector source and provider identifier."""

        result = await self.session.scalars(
            select(Publication)
            .where(Publication.source == source, Publication.external_id == external_id)
            .limit(1)
        )
        return result.first()

    async def find_by_title_year_first_author(
        self,
        *,
        normalized_title: str,
        publication_year: int | None,
        first_author_normalized: str | None,
    ) -> Publication | None:
        """Match by normalized title, year, and first author."""

        if not normalized_title or publication_year is None or not first_author_normalized:
            return None
        statement = (
            select(Publication)
            .join(PublicationAuthor, PublicationAuthor.publication_id == Publication.id)
            .join(Author, Author.id == PublicationAuthor.author_id)
            .where(
                Publication.normalized_title == normalized_title,
                Publication.publication_year == publication_year,
                PublicationAuthor.author_order == 1,
                Author.normalized_name == first_author_normalized,
            )
            .limit(1)
        )
        result = await self.session.scalars(statement)
        return result.first()

    async def title_similarity_candidates(
        self,
        *,
        publication_year: int | None,
        limit: int = 100,
    ) -> Sequence[Publication]:
        """Return candidate publications for Python-side title similarity matching."""

        statement = select(Publication).where(Publication.is_deleted.is_(False))
        if publication_year:
            statement = statement.where(Publication.publication_year == publication_year)
        statement = statement.order_by(desc(Publication.updated_at)).limit(limit)
        result = await self.session.scalars(statement)
        return result.all()

    async def attach_author(
        self,
        *,
        publication_id: UUID,
        author_id: UUID,
        author_order: int,
        affiliation: str | None = None,
        orcid: str | None = None,
    ) -> PublicationAuthor:
        """Attach an author to a publication."""

        join = PublicationAuthor(
            publication_id=publication_id,
            author_id=author_id,
            author_order=author_order,
            affiliation=affiliation,
            orcid=orcid,
        )
        self.session.add(join)
        await self.session.flush()
        return join

    async def attach_keyword(
        self,
        *,
        publication_id: UUID,
        keyword_id: UUID,
    ) -> PublicationKeyword:
        """Attach a keyword to a publication."""

        join = PublicationKeyword(publication_id=publication_id, keyword_id=keyword_id)
        self.session.add(join)
        await self.session.flush()
        return join

    def _filtered_statement(
        self, filters: PublicationFilters | None = None
    ) -> Select[tuple[Publication]]:
        statement = self.with_relations(select(Publication).distinct())
        if filters is None:
            return statement
        if filters.repository_id:
            statement = statement.where(Publication.repository_id == filters.repository_id)
        if filters.source:
            statement = statement.where(Publication.source == filters.source)
        if filters.source_type:
            statement = statement.where(Publication.source_type == filters.source_type)
        if filters.q:
            q = f"%{filters.q}%"
            statement = statement.where(
                or_(Publication.title.ilike(q), Publication.abstract.ilike(q))
            )
        if filters.author:
            q = f"%{_normalize_filter(filters.author)}%"
            statement = (
                statement.join(
                    PublicationAuthor, PublicationAuthor.publication_id == Publication.id
                )
                .join(Author, Author.id == PublicationAuthor.author_id)
                .where(Author.normalized_name.ilike(q))
            )
        if filters.keyword:
            q = f"%{_normalize_filter(filters.keyword)}%"
            statement = (
                statement.join(
                    PublicationKeyword, PublicationKeyword.publication_id == Publication.id
                )
                .join(Keyword, Keyword.id == PublicationKeyword.keyword_id)
                .where(Keyword.normalized_term.ilike(q))
            )
        if filters.year:
            statement = statement.where(Publication.publication_year == filters.year)
        if filters.year_from:
            statement = statement.where(Publication.publication_year >= filters.year_from)
        if filters.year_to:
            statement = statement.where(Publication.publication_year <= filters.year_to)
        if filters.language:
            statement = statement.where(Publication.language == filters.language)
        if filters.doi:
            statement = statement.where(Publication.doi == filters.doi)
        if filters.is_deleted is not None:
            statement = statement.where(Publication.is_deleted.is_(filters.is_deleted))
        return statement


class HarvestJobRepository(AsyncRepository[HarvestJob]):
    """Repository for harvest job CRUD and operational filtering."""

    model = HarvestJob

    def _filtered_statement(
        self, filters: HarvestJobFilters | None = None
    ) -> Select[tuple[HarvestJob]]:
        statement = select(HarvestJob)
        if filters is None:
            return statement
        if filters.connector_id:
            statement = statement.where(HarvestJob.connector_id == filters.connector_id)
        if filters.status:
            statement = statement.where(HarvestJob.status == filters.status)
        if filters.since_year:
            statement = statement.where(
                func.extract("year", HarvestJob.since) == filters.since_year
            )
        if filters.has_errors is not None:
            statement = statement.where(
                HarvestJob.error_count > 0 if filters.has_errors else HarvestJob.error_count == 0
            )
        return statement

    def _ordered_statement(self, statement: Select[tuple[HarvestJob]]) -> Select[tuple[HarvestJob]]:
        return statement.order_by(desc(HarvestJob.created_at))


class QualityReportRepository(AsyncRepository[QualityReport]):
    """Repository for metadata quality assessment history and latest reports."""

    model = QualityReport

    def query(
        self,
        filters: QualityReportFilters | None = None,
        pagination: Pagination | None = None,
    ) -> Select[tuple[QualityReport]]:
        """Build a filtered, sorted, paginated SELECT for quality reports."""

        statement = self._apply_ordering(self._filtered_statement(filters), filters)
        if pagination:
            page = pagination.normalized()
            statement = statement.limit(page.limit).offset(page.offset)
        return statement

    async def latest_for_publication(self, publication_id: UUID) -> QualityReport | None:
        """Return the current quality report for a publication, if one exists."""

        result = await self.session.scalars(
            select(QualityReport)
            .where(
                QualityReport.publication_id == publication_id,
                QualityReport.is_current.is_(True),
            )
            .order_by(desc(QualityReport.assessed_at))
            .limit(1)
        )
        return result.first()

    async def mark_previous_not_current(self, publication_id: UUID) -> int:
        """Mark existing current reports for a publication as historical."""

        reports = await self.session.scalars(
            select(QualityReport).where(
                QualityReport.publication_id == publication_id,
                QualityReport.is_current.is_(True),
            )
        )
        changed = 0
        for report in reports:
            report.is_current = False
            changed += 1
        await self.session.flush()
        return changed

    def _filtered_statement(
        self, filters: QualityReportFilters | None = None
    ) -> Select[tuple[QualityReport]]:
        statement = select(QualityReport).join(
            Publication, QualityReport.publication_id == Publication.id
        )
        if filters is None:
            return statement
        if filters.publication_id:
            statement = statement.where(QualityReport.publication_id == filters.publication_id)
        if filters.grade:
            statement = statement.where(QualityReport.grade == filters.grade.upper())
        if filters.min_score is not None:
            statement = statement.where(QualityReport.final_score >= filters.min_score)
        if filters.max_score is not None:
            statement = statement.where(QualityReport.final_score <= filters.max_score)
        if filters.issue_type:
            statement = statement.where(QualityReport.issue_types.contains([filters.issue_type]))
        if filters.repository_id:
            statement = statement.where(Publication.repository_id == filters.repository_id)
        if filters.journal_id:
            statement = statement.where(Publication.journal_id == filters.journal_id)
        if filters.year:
            statement = statement.where(Publication.publication_year == filters.year)
        if filters.is_deleted is not None:
            statement = statement.where(Publication.is_deleted.is_(filters.is_deleted))
        if filters.is_current is not None:
            statement = statement.where(QualityReport.is_current.is_(filters.is_current))
        if filters.university_id:
            statement = statement.join(
                RepositoryModel, RepositoryModel.id == Publication.repository_id
            ).where(RepositoryModel.university_id == filters.university_id)
        return statement

    def _apply_ordering(
        self,
        statement: Select[tuple[QualityReport]],
        filters: QualityReportFilters | None,
    ) -> Select[tuple[QualityReport]]:
        """Apply caller-selected quality report ordering."""

        sort_column: InstrumentedAttribute[Any] = QualityReport.assessed_at
        sort_by = filters.sort_by if filters else "assessed_at"
        sort_order = filters.sort_order.lower() if filters else "desc"
        if sort_by == "final_score":
            sort_column = QualityReport.final_score
        elif sort_by == "grade":
            sort_column = QualityReport.grade
        elif sort_by == "generated_at":
            sort_column = QualityReport.generated_at
        elif sort_by == "completeness_score":
            sort_column = QualityReport.completeness_score
        elif sort_by == "validity_score":
            sort_column = QualityReport.validity_score
        if sort_order == "asc":
            return statement.order_by(sort_column)
        return statement.order_by(desc(sort_column))


def _normalize_filter(value: str) -> str:
    """Normalize free-text filter values to match stored normalized fields."""

    return " ".join(value.casefold().strip().split())
