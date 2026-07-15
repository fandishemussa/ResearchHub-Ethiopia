"""Application services for catalog, storage, search, analytics, and harvesting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from researchhub_ai.embeddings import Encoder, normalize_whitespace
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from researchhub.domain.schemas import (
    ConnectorCreate,
    HarvestRequest,
    PublicationCreate,
    RepositoryCreate,
    SearchQuery,
    UniversityCreate,
)
from researchhub.domain.value_objects import normalize_doi, normalize_orcid
from researchhub.infrastructure.persistence.models import (
    Author,
    Connector,
    HarvestJob,
    Journal,
    Keyword,
    Publication,
    PublicationAuthor,
    PublicationKeyword,
    PublicationType,
    QualityReport,
    Repository,
    University,
)
from researchhub.infrastructure.persistence.repositories import (
    AuthorFilters,
    AuthorRepository,
    HarvestJobFilters,
    HarvestJobRepository,
    InstitutionalRepositoryRepository,
    KeywordFilters,
    KeywordRepository,
    PublicationFilters,
    PublicationRepository,
    RepositoryFilters,
    UniversityFilters,
    UniversityRepository,
)
from researchhub.infrastructure.persistence.transactions import transaction


def _url_to_str(value: Any) -> str | None:
    """Convert Pydantic URL values to strings without leaking implementation types."""

    return str(value) if value is not None else None


def _normalize_name(value: str) -> str:
    """Normalize names and terms for matching while preserving display values elsewhere."""

    return " ".join(value.casefold().strip().split())


def _score_publication(payload: PublicationCreate) -> Decimal:
    """Calculate a first-pass quality score from completeness and identifier strength."""

    required = [
        payload.title,
        payload.authors,
        payload.publication_year or payload.publication_date,
        payload.source,
        payload.source_type,
    ]
    optional = [
        payload.abstract,
        payload.doi,
        payload.keywords,
        payload.language,
        payload.article_url or payload.pdf_url,
        payload.publisher,
    ]
    score = sum(1 for value in required if value) * 12
    score += sum(1 for value in optional if value) * 6
    if payload.doi:
        score += 10
    return Decimal(min(score, 100)).quantize(Decimal("0.01"))


class UniversityService:
    """Transactional CRUD service for universities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = UniversityRepository(session)

    async def create(self, payload: UniversityCreate) -> University:
        """Register a university."""

        university = University(
            code=payload.code.upper(),
            name=payload.name,
            country=payload.country,
            city=payload.city,
            website_url=_url_to_str(payload.website_url),
            metadata_json=payload.metadata,
        )
        async with transaction(self.session):
            await self.repository.add(university)
        await self.session.refresh(university)
        return university

    async def get(self, university_id: UUID) -> University | None:
        """Return a university by UUID."""

        return await self.repository.get(university_id)

    async def list(
        self,
        *,
        q: str | None = None,
        country: str | None = None,
        city: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[University]:
        """List universities with pagination and filtering."""

        return await self.repository.list(
            UniversityFilters(q=q, country=country, city=city, is_active=is_active),
            limit=limit,
            offset=offset,
        )

    async def update(self, university_id: UUID, values: Mapping[str, Any]) -> University | None:
        """Update a university."""

        if "code" in values and values["code"]:
            values = {**values, "code": str(values["code"]).upper()}
        async with transaction(self.session):
            university = await self.repository.update(university_id, values)
        if university:
            await self.session.refresh(university)
        return university

    async def delete(self, university_id: UUID, *, hard: bool = False) -> bool:
        """Soft-delete or hard-delete a university."""

        async with transaction(self.session):
            return await self.repository.delete(university_id, hard=hard)


class RepositoryService:
    """Transactional CRUD service for institutional repositories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = InstitutionalRepositoryRepository(session)

    async def create(self, payload: RepositoryCreate) -> Repository:
        """Register a repository, DSpace endpoint, OJS site, or related source."""

        repository = Repository(
            university_id=payload.university_id,
            name=payload.name,
            platform=payload.platform,
            base_url=_url_to_str(payload.base_url) or "",
            oai_endpoint=_url_to_str(payload.oai_endpoint),
            metadata_formats=payload.metadata_formats,
        )
        async with transaction(self.session):
            await self.repository.add(repository)
        await self.session.refresh(repository)
        return repository

    async def get(self, repository_id: UUID) -> Repository | None:
        """Return a repository by UUID."""

        return await self.repository.get(repository_id)

    async def list(
        self,
        *,
        university_id: UUID | None = None,
        platform: str | None = None,
        q: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Repository]:
        """List repositories with pagination and filtering."""

        return await self.repository.list(
            RepositoryFilters(
                university_id=university_id,
                platform=platform,
                q=q,
                is_active=is_active,
            ),
            limit=limit,
            offset=offset,
        )

    async def update(self, repository_id: UUID, values: Mapping[str, Any]) -> Repository | None:
        """Update a repository."""

        values = {
            key: _url_to_str(value) if key in {"base_url", "oai_endpoint"} else value
            for key, value in values.items()
        }
        async with transaction(self.session):
            repository = await self.repository.update(repository_id, values)
        if repository:
            await self.session.refresh(repository)
        return repository

    async def delete(self, repository_id: UUID, *, hard: bool = False) -> bool:
        """Soft-delete or hard-delete a repository."""

        async with transaction(self.session):
            return await self.repository.delete(repository_id, hard=hard)


class AuthorService:
    """Transactional CRUD service for authors."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AuthorRepository(session)

    async def get_or_create(self, full_name: str, *, orcid: str | None = None) -> Author:
        """Find an author by ORCID/name or create one."""

        normalized = _normalize_name(full_name)
        existing = None
        if orcid:
            existing = await self.repository.get_by_orcid(normalize_orcid(orcid) or orcid)
        if existing is None:
            existing = await self.repository.get_by_normalized_name(normalized)
        if existing:
            return existing
        author = Author(
            full_name=full_name.strip(),
            normalized_name=normalized,
            orcid=normalize_orcid(orcid),
        )
        await self.repository.add(author)
        return author

    async def list(
        self,
        *,
        q: str | None = None,
        orcid: str | None = None,
        university_id: UUID | None = None,
        department_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Author]:
        """List authors with pagination and filtering."""

        return await self.repository.list(
            AuthorFilters(
                q=q, orcid=orcid, university_id=university_id, department_id=department_id
            ),
            limit=limit,
            offset=offset,
        )

    async def update(self, author_id: UUID, values: Mapping[str, Any]) -> Author | None:
        """Update an author."""

        if "full_name" in values and values["full_name"]:
            values = {**values, "normalized_name": _normalize_name(str(values["full_name"]))}
        if "orcid" in values and values["orcid"]:
            values = {**values, "orcid": normalize_orcid(str(values["orcid"]))}
        async with transaction(self.session):
            author = await self.repository.update(author_id, values)
        if author:
            await self.session.refresh(author)
        return author

    async def delete(self, author_id: UUID, *, hard: bool = True) -> bool:
        """Delete an author."""

        async with transaction(self.session):
            return await self.repository.delete(author_id, hard=hard)


class KeywordService:
    """Transactional CRUD service for keywords."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = KeywordRepository(session)

    async def get_or_create(self, term: str, *, vocabulary: str | None = None) -> Keyword:
        """Find a keyword by normalized term or create one."""

        normalized = _normalize_name(term)
        existing = await self.repository.get_by_normalized_term(normalized)
        if existing:
            return existing
        keyword = Keyword(term=term.strip(), normalized_term=normalized, vocabulary=vocabulary)
        await self.repository.add(keyword)
        return keyword

    async def list(
        self,
        *,
        q: str | None = None,
        vocabulary: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Keyword]:
        """List keywords with pagination and filtering."""

        return await self.repository.list(
            KeywordFilters(q=q, vocabulary=vocabulary),
            limit=limit,
            offset=offset,
        )

    async def update(self, keyword_id: UUID, values: Mapping[str, Any]) -> Keyword | None:
        """Update a keyword."""

        if "term" in values and values["term"]:
            values = {**values, "normalized_term": _normalize_name(str(values["term"]))}
        async with transaction(self.session):
            keyword = await self.repository.update(keyword_id, values)
        if keyword:
            await self.session.refresh(keyword)
        return keyword

    async def delete(self, keyword_id: UUID, *, hard: bool = True) -> bool:
        """Delete a keyword."""

        async with transaction(self.session):
            return await self.repository.delete(keyword_id, hard=hard)


class CatalogService:
    """Backward-compatible facade for catalog routes."""

    def __init__(self, session: AsyncSession) -> None:
        self.universities = UniversityService(session)
        self.repositories = RepositoryService(session)
        self.authors = AuthorService(session)

    async def create_university(self, payload: UniversityCreate) -> University:
        """Register a university."""

        return await self.universities.create(payload)

    async def list_universities(self, limit: int = 50, offset: int = 0) -> Sequence[University]:
        """List registered universities."""

        return await self.universities.list(limit=limit, offset=offset)

    async def create_repository(self, payload: RepositoryCreate) -> Repository:
        """Register a repository or source."""

        return await self.repositories.create(payload)

    async def list_repositories(self, limit: int = 50, offset: int = 0) -> Sequence[Repository]:
        """List configured repositories."""

        return await self.repositories.list(limit=limit, offset=offset)

    async def get_repository(self, repository_id: UUID) -> Repository | None:
        return await self.repositories.get(repository_id)

    async def update_repository(
        self, repository_id: UUID, values: Mapping[str, Any]
    ) -> Repository | None:
        return await self.repositories.update(repository_id, values)

    async def delete_repository(self, repository_id: UUID) -> bool:
        return await self.repositories.delete(repository_id)

    async def list_authors(self, limit: int = 50, offset: int = 0) -> Sequence[Author]:
        """List known authors."""

        return await self.authors.list(limit=limit, offset=offset)


class PublicationService:
    """Transactional CRUD service for normalized publications."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PublicationRepository(session)
        self.authors = AuthorService(session)
        self.keywords = KeywordService(session)

    async def create_publication(self, payload: PublicationCreate) -> Publication:
        """Create a publication with author and keyword joins atomically."""

        publication = Publication(
            external_id=payload.external_id,
            title=payload.title.strip(),
            abstract=payload.abstract,
            affiliations=payload.affiliations,
            publisher=payload.publisher,
            publication_date=payload.publication_date,
            publication_year=payload.publication_year,
            subjects=payload.subjects,
            language=payload.language,
            doi=normalize_doi(payload.doi),
            issn=payload.issn,
            isbn=payload.isbn,
            license=payload.license,
            article_url=_url_to_str(payload.article_url),
            pdf_url=_url_to_str(payload.pdf_url),
            repository_id=payload.repository_id,
            repository_identifier=payload.repository_identifier,
            source=payload.source,
            source_type=payload.source_type,
            harvested_at=datetime.now(UTC),
            quality_score=_score_publication(payload),
            raw_record=payload.raw_record,
        )

        async with transaction(self.session):
            await self.repository.add(publication)
            for index, author_name in enumerate(payload.authors, start=1):
                author = await self.authors.get_or_create(author_name)
                await self.repository.attach_author(
                    publication_id=publication.id,
                    author_id=author.id,
                    author_order=index,
                    affiliation=payload.affiliations[index - 1]
                    if index <= len(payload.affiliations)
                    else None,
                    orcid=normalize_orcid(author.orcid),
                )
            for keyword_text in payload.keywords:
                keyword = await self.keywords.get_or_create(keyword_text)
                await self.repository.attach_keyword(
                    publication_id=publication.id,
                    keyword_id=keyword.id,
                )

        await self.session.refresh(publication)
        return publication

    async def get(self, publication_id: UUID) -> Publication | None:
        """Return a publication by UUID."""

        return await self.repository.get(publication_id)

    async def list_publications(
        self,
        *,
        repository_id: UUID | None = None,
        source: str | None = None,
        source_type: str | None = None,
        q: str | None = None,
        year: int | None = None,
        language: str | None = None,
        is_deleted: bool | None = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Publication]:
        """List publications with pagination and filtering."""

        return await self.repository.list(
            PublicationFilters(
                repository_id=repository_id,
                source=source,
                source_type=source_type,
                q=q,
                year=year,
                language=language,
                is_deleted=is_deleted,
            ),
            limit=limit,
            offset=offset,
        )

    async def update(self, publication_id: UUID, values: Mapping[str, Any]) -> Publication | None:
        """Update a publication."""

        if "doi" in values and values["doi"]:
            values = {**values, "doi": normalize_doi(str(values["doi"]))}
        async with transaction(self.session):
            publication = await self.repository.update(publication_id, values)
        if publication:
            await self.session.refresh(publication)
        return publication

    async def delete(self, publication_id: UUID, *, hard: bool = False) -> bool:
        """Soft-delete or hard-delete a publication."""

        async with transaction(self.session):
            return await self.repository.delete(publication_id, hard=hard)


class SearchService:
    """Search use cases backed by PostgreSQL full text and normalized joins."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.publications = PublicationRepository(session)

    async def search_publications(self, query: SearchQuery) -> Sequence[Publication]:
        """Search publications by title, author, keyword, journal, year, and language."""

        if query.journal:
            statement = (
                select(Publication)
                .distinct()
                .join(Journal)
                .options(
                    selectinload(Publication.authors).selectinload(PublicationAuthor.author),
                    selectinload(Publication.keywords).selectinload(PublicationKeyword.keyword),
                )
            )
            statement = statement.where(Journal.name.ilike(f"%{query.journal}%"))
            if query.q:
                ts_query = func.plainto_tsquery("simple", query.q)
                statement = statement.where(
                    or_(
                        Publication.search_vector.op("@@")(ts_query),
                        Publication.title.ilike(f"%{query.q}%"),
                    )
                )
            statement = (
                statement.order_by(desc(Publication.updated_at))
                .limit(query.limit)
                .offset(query.offset)
            )
            result = await self.session.scalars(statement)
            return result.unique().all()

        return await self.publications.list(
            PublicationFilters(
                q=query.q,
                author=query.author,
                keyword=query.keyword,
                year=query.year,
                language=query.language,
                is_deleted=False,
            ),
            limit=query.limit,
            offset=query.offset,
        )


def semantic_search_statement(
    query_vector: list[float],
    *,
    limit: int,
    source: str | None = None,
    min_similarity: float | None = None,
) -> Select[tuple[Publication, float]]:
    """Build a filtered database-native cosine nearest-neighbor query."""

    distance = Publication.embedding.cosine_distance(query_vector)
    similarity = (1 - distance).label("similarity")
    statement = select(Publication, similarity).where(
        Publication.embedding.is_not(None),
        Publication.is_deleted.is_(False),
    )
    if source:
        statement = statement.where(Publication.source == source)
    if min_similarity is not None:
        statement = statement.where(similarity >= min_similarity)
    return statement.order_by(distance).limit(limit)


class SemanticSearchService:
    """Database-native pgvector cosine nearest-neighbor search."""

    def __init__(self, session: AsyncSession, encoder: Encoder) -> None:
        self.session = session
        self.encoder = encoder

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        source: str | None = None,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        normalized_query = normalize_whitespace(query)
        if not normalized_query:
            raise ValueError("Semantic search query must not be blank")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if min_similarity is not None and not 0 <= min_similarity <= 1:
            raise ValueError("min_similarity must be between 0 and 1")

        query_vector = self.encoder.encode_query(normalized_query)
        statement = semantic_search_statement(
            query_vector,
            limit=limit,
            source=source,
            min_similarity=min_similarity,
        )
        rows = (await self.session.execute(statement)).all()
        return [
            {
                "id": publication.id,
                "title": publication.title,
                "abstract_preview": publication.abstract[:500] if publication.abstract else None,
                "publication_year": publication.publication_year,
                "source": publication.source,
                "article_url": publication.article_url,
                "similarity": float(score),
            }
            for publication, score in rows
        ]


def publication_similarity_statement(
    embedding: list[float],
    *,
    publication_id: UUID,
    limit: int,
    minimum_score: float | None = None,
    university_id: UUID | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    publication_type: str | None = None,
) -> Select[tuple[Publication, float]]:
    """Build a filtered pgvector nearest-neighbor query for one publication."""

    distance = Publication.embedding.cosine_distance(embedding)
    similarity = (1 - distance).label("similarity_score")
    statement = (
        select(Publication, similarity)
        .options(
            selectinload(Publication.authors).selectinload(PublicationAuthor.author),
            selectinload(Publication.keywords).selectinload(PublicationKeyword.keyword),
        )
        .where(
            Publication.id != publication_id,
            Publication.embedding.is_not(None),
            Publication.is_deleted.is_(False),
        )
    )
    if minimum_score is not None:
        statement = statement.where(similarity >= minimum_score)
    if university_id is not None:
        statement = statement.join(Repository).where(Repository.university_id == university_id)
    if year_from is not None:
        statement = statement.where(Publication.publication_year >= year_from)
    if year_to is not None:
        statement = statement.where(Publication.publication_year <= year_to)
    if publication_type:
        statement = statement.join(PublicationType).where(
            or_(
                PublicationType.name.ilike(publication_type),
                PublicationType.normalized_name
                == normalize_whitespace(publication_type).casefold(),
            )
        )
    return statement.order_by(distance).limit(limit)


class PublicationSimilarityService:
    """Find explainable nearest neighbors for an embedded publication."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.publications = PublicationRepository(session)

    async def similar(
        self,
        publication_id: UUID,
        *,
        limit: int = 10,
        minimum_score: float | None = None,
        university_id: UUID | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        publication_type: str | None = None,
    ) -> tuple[Publication, list[dict[str, Any]]]:
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if minimum_score is not None and not 0 <= minimum_score <= 1:
            raise ValueError("minimum_score must be between 0 and 1")
        if year_from is not None and year_to is not None and year_from > year_to:
            raise ValueError("year_from must be less than or equal to year_to")

        target = await self.publications.get(publication_id)
        if target is None or target.is_deleted:
            raise LookupError("Publication not found")
        if target.embedding is None:
            raise RuntimeError("Publication embedding is not available")

        statement = publication_similarity_statement(
            list(target.embedding),
            publication_id=publication_id,
            limit=limit,
            minimum_score=minimum_score,
            university_id=university_id,
            year_from=year_from,
            year_to=year_to,
            publication_type=publication_type,
        )
        rows = (await self.session.execute(statement)).all()
        target_keywords = {
            link.keyword.term.casefold(): link.keyword.term
            for link in target.keywords
            if link.keyword and link.keyword.term
        }
        target_topics = {
            topic.casefold(): topic for topic in target.subjects if isinstance(topic, str)
        }
        results: list[dict[str, Any]] = []
        for candidate, score in rows:
            candidate_keywords = {
                link.keyword.term.casefold(): link.keyword.term
                for link in candidate.keywords
                if link.keyword and link.keyword.term
            }
            candidate_topics = {
                topic.casefold(): topic for topic in candidate.subjects if isinstance(topic, str)
            }
            shared_keywords = [
                target_keywords[key] for key in target_keywords.keys() & candidate_keywords
            ]
            shared_topics = [target_topics[key] for key in target_topics.keys() & candidate_topics]
            explanation = ["Ranked by cosine similarity between publication embeddings."]
            if shared_keywords:
                explanation.append(f"Shares {len(shared_keywords)} normalized keyword(s).")
            if shared_topics:
                explanation.append(f"Shares {len(shared_topics)} subject topic(s).")
            results.append(
                {
                    "id": candidate.id,
                    "title": candidate.title,
                    "abstract_preview": candidate.abstract[:500] if candidate.abstract else None,
                    "publication_year": candidate.publication_year,
                    "source": candidate.source,
                    "article_url": candidate.article_url,
                    "similarity_score": float(score),
                    "shared_keywords": shared_keywords,
                    "shared_topics": shared_topics,
                    "explanation": explanation,
                }
            )
        return target, results


class AnalyticsService:
    """Read models for dashboards and institutional reporting."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publication_counts(self) -> dict[str, Any]:
        """Return headline publication counts for dashboards."""

        total = await self.session.scalar(select(func.count(Publication.id)))
        deleted = await self.session.scalar(
            select(func.count(Publication.id)).where(Publication.is_deleted.is_(True))
        )
        return {"total_publications": total or 0, "deleted_publications": deleted or 0}

    async def publication_trends(self) -> list[dict[str, Any]]:
        """Return annual publication trends."""

        rows = await self.session.execute(
            select(Publication.publication_year, func.count(Publication.id))
            .where(Publication.publication_year.is_not(None))
            .group_by(Publication.publication_year)
            .order_by(Publication.publication_year)
        )
        return [{"year": year, "count": count} for year, count in rows]

    async def keyword_trends(self, limit: int = 25) -> list[dict[str, Any]]:
        """Return top keywords by publication occurrence."""

        rows = await self.session.execute(
            select(Keyword.term, func.count(Publication.id).label("count"))
            .join(PublicationKeyword, Keyword.id == PublicationKeyword.keyword_id)
            .join(Publication, Publication.id == PublicationKeyword.publication_id)
            .group_by(Keyword.term)
            .order_by(desc("count"))
            .limit(limit)
        )
        return [{"keyword": term, "count": count} for term, count in rows]

    async def source_status(self) -> list[dict[str, Any]]:
        """Return managed-source harvest recency and publication totals."""

        connector_rows = await self.session.execute(
            select(
                Connector.name,
                Connector.connector_type,
                Connector.enabled,
                Connector.status,
                Connector.last_harvested_at,
                func.count(Publication.id).label("publication_count"),
            )
            .outerjoin(Publication, Publication.source == Connector.code)
            .where(Connector.status != "removed")
            .group_by(Connector.id)
            .order_by(Connector.name)
        )
        return [
            {
                "name": name,
                "platform": connector_type.replace("_", "-"),
                "is_active": enabled and connector_status == "active",
                "last_harvested_at": last_harvested_at,
                "publication_count": publication_count,
            }
            for (
                name,
                connector_type,
                enabled,
                connector_status,
                last_harvested_at,
                publication_count,
            ) in connector_rows
        ]


class HarvestJobService:
    """Transactional CRUD service for harvest jobs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = HarvestJobRepository(session)

    async def create(self, payload: HarvestRequest) -> HarvestJob:
        """Create a harvest job."""

        job = HarvestJob(
            connector_id=payload.connector_id,
            status="queued",
            since=payload.since,
            until=payload.until,
            metadata_json={
                "metadata_prefix": payload.metadata_prefix,
                "set_spec": payload.set_spec,
            },
        )
        async with transaction(self.session):
            await self.repository.add(job)
        await self.session.refresh(job)
        return job

    async def list(
        self,
        *,
        connector_id: UUID | None = None,
        status: str | None = None,
        since_year: int | None = None,
        has_errors: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[HarvestJob]:
        """List harvest jobs with pagination and filtering."""

        return await self.repository.list(
            HarvestJobFilters(
                connector_id=connector_id,
                status=status,
                since_year=since_year,
                has_errors=has_errors,
            ),
            limit=limit,
            offset=offset,
        )

    async def update(self, job_id: UUID, values: Mapping[str, Any]) -> HarvestJob | None:
        """Update a harvest job."""

        async with transaction(self.session):
            job = await self.repository.update(job_id, values)
        if job:
            await self.session.refresh(job)
        return job

    async def delete(self, job_id: UUID, *, hard: bool = True) -> bool:
        """Delete a harvest job."""

        async with transaction(self.session):
            return await self.repository.delete(job_id, hard=hard)


class ConnectorService:
    """Connector configuration and harvest job use cases."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.harvest_jobs = HarvestJobService(session)

    async def create_connector(self, payload: ConnectorCreate) -> Connector:
        """Register a connector configuration."""

        connector = Connector(
            code=payload.code,
            name=payload.name,
            connector_type=payload.connector_type,
            base_url=_url_to_str(payload.base_url),
            university_id=payload.university_id,
            repository_id=payload.repository_id,
            config=payload.config,
            schedule=payload.schedule,
        )
        async with transaction(self.session):
            self.session.add(connector)
            await self.session.flush()
        await self.session.refresh(connector)
        return connector

    async def list_connectors(self, limit: int = 50, offset: int = 0) -> Sequence[Connector]:
        """List connector configurations."""

        statement = (
            select(Connector).order_by(desc(Connector.created_at)).limit(limit).offset(offset)
        )
        result = await self.session.scalars(statement)
        return result.all()

    async def queue_harvest(self, payload: HarvestRequest) -> HarvestJob:
        """Create a harvest job record for a worker to execute."""

        return await self.harvest_jobs.create(payload)


class QualityService:
    """Metadata quality reporting use cases."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_reports(self, limit: int = 50, offset: int = 0) -> Sequence[QualityReport]:
        """List latest quality reports."""

        statement = (
            select(QualityReport)
            .order_by(desc(QualityReport.generated_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(statement)
        return result.all()
