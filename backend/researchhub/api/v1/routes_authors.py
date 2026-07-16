"""Author discovery endpoints."""

from fastapi import APIRouter, Depends, Query

from researchhub.api.v1.dependencies import get_catalog_service, require_permission
from researchhub.application.services import CatalogService
from researchhub.core.permissions import Permissions
from researchhub.domain.schemas import AuthorRead

router = APIRouter(
    prefix="/authors",
    tags=["authors"],
    dependencies=[Depends(require_permission(Permissions.PUBLICATIONS_READ))],
)


@router.get("", response_model=list[AuthorRead])
async def list_authors(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: CatalogService = Depends(get_catalog_service),
) -> list[AuthorRead]:
    """List normalized author records."""

    authors = await service.list_authors(limit=limit, offset=offset)
    return [AuthorRead.model_validate(item) for item in authors]
