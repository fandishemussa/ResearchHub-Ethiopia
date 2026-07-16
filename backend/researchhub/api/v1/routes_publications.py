"""Publication ingestion and listing endpoints."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from researchhub.api.v1.dependencies import get_publication_service, require_permission
from researchhub.application.services import PublicationService
from researchhub.core.permissions import Permissions
from researchhub.domain.schemas import PublicationCreate, PublicationRead
from researchhub.infrastructure.persistence.models import Publication

router = APIRouter(
    prefix="/publications",
    tags=["publications"],
    dependencies=[Depends(require_permission(Permissions.PUBLICATIONS_READ))],
)


def publication_response(
    publication: Publication,
    *,
    authors: list[str] | None = None,
    keywords: list[str] | None = None,
    subjects: list[str] | None = None,
) -> PublicationRead:
    """Map the ORM aggregate into the stable public publication schema."""

    resolved_authors = authors
    if resolved_authors is None:
        resolved_authors = [
            link.author.full_name
            for link in sorted(publication.authors, key=lambda item: item.author_order)
            if link.author and link.author.full_name
        ]
    resolved_keywords = keywords
    if resolved_keywords is None:
        resolved_keywords = [
            link.keyword.term
            for link in publication.keywords
            if link.keyword and link.keyword.term
        ]

    return PublicationRead.model_validate(
        {
            "id": publication.id,
            "external_id": publication.external_id,
            "title": publication.title,
            "abstract": publication.abstract,
            "publication_date": publication.publication_date,
            "publication_year": publication.publication_year,
            "language": publication.language,
            "doi": publication.doi,
            "issn": publication.issn,
            "isbn": publication.isbn,
            "license": publication.license,
            "article_url": publication.article_url,
            "pdf_url": publication.pdf_url,
            "publisher": publication.publisher,
            "source": publication.source,
            "source_type": publication.source_type,
            "repository_id": publication.repository_id,
            "repository_identifier": publication.repository_identifier,
            "authors": resolved_authors,
            "affiliations": publication.affiliations or [],
            "keywords": resolved_keywords,
            "subjects": subjects or publication.subjects or [],
            "raw_record": publication.raw_record or {},
            "harvested_at": publication.harvested_at,
            "updated_at": publication.updated_at,
            "quality_score": publication.quality_score or Decimal("0.00"),
            "is_deleted": publication.is_deleted,
        }
    )


@router.get("", response_model=list[PublicationRead])
async def list_publications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: PublicationService = Depends(get_publication_service),
) -> list[PublicationRead]:
    """List normalized publications."""

    publications = await service.list_publications(limit=limit, offset=offset)
    return [publication_response(item) for item in publications]


@router.get("/{publication_id}", response_model=PublicationRead)
async def get_publication(
    publication_id: UUID,
    service: PublicationService = Depends(get_publication_service),
) -> PublicationRead:
    """Return one active publication with authors and keywords."""

    publication = await service.get(publication_id)
    if publication is None or publication.is_deleted:
        raise HTTPException(status_code=404, detail="Publication not found")
    return publication_response(publication)


@router.post(
    "",
    response_model=PublicationRead,
    status_code=201,
    dependencies=[Depends(require_permission(Permissions.PUBLICATIONS_MANAGE))],
)
async def create_publication(
    payload: PublicationCreate,
    service: PublicationService = Depends(get_publication_service),
) -> PublicationRead:
    """Create a normalized publication record."""

    publication = await service.create_publication(payload)
    return publication_response(
        publication,
        authors=payload.authors,
        keywords=payload.keywords,
        subjects=payload.subjects,
    )
