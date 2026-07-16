"""University catalog endpoints."""

from fastapi import APIRouter, Depends, Query

from researchhub.api.v1.dependencies import get_catalog_service, require_permission
from researchhub.application.services import CatalogService
from researchhub.core.permissions import Permissions
from researchhub.domain.schemas import UniversityCreate, UniversityRead

router = APIRouter(
    prefix="/universities",
    tags=["universities"],
    dependencies=[Depends(require_permission(Permissions.PUBLICATIONS_READ))],
)


@router.get("", response_model=list[UniversityRead])
async def list_universities(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: CatalogService = Depends(get_catalog_service),
) -> list[UniversityRead]:
    """List registered universities."""

    universities = await service.list_universities(limit=limit, offset=offset)
    return [UniversityRead.model_validate(item) for item in universities]


@router.post(
    "",
    response_model=UniversityRead,
    status_code=201,
    dependencies=[Depends(require_permission(Permissions.SETTINGS_MANAGE))],
)
async def create_university(
    payload: UniversityCreate,
    service: CatalogService = Depends(get_catalog_service),
) -> UniversityRead:
    """Register a university."""

    university = await service.create_university(payload)
    return UniversityRead.model_validate(university)
