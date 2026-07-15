"""Repository and source endpoint APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from researchhub.api.v1.dependencies import get_catalog_service
from researchhub.application.services import CatalogService
from researchhub.domain.schemas import RepositoryCreate, RepositoryRead, RepositoryUpdate

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryRead])
async def list_repositories(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: CatalogService = Depends(get_catalog_service),
) -> list[RepositoryRead]:
    """List configured institutional repositories and journal platforms."""

    repositories = await service.list_repositories(limit=limit, offset=offset)
    return [RepositoryRead.model_validate(item) for item in repositories]


@router.post("", response_model=RepositoryRead, status_code=201)
async def create_repository(
    payload: RepositoryCreate,
    service: CatalogService = Depends(get_catalog_service),
) -> RepositoryRead:
    """Register a repository, DSpace endpoint, OJS site, or equivalent source."""

    repository = await service.create_repository(payload)
    return RepositoryRead.model_validate(repository)


@router.get("/{repository_id}", response_model=RepositoryRead)
async def get_repository(
    repository_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> RepositoryRead:
    repository = await service.get_repository(repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return RepositoryRead.model_validate(repository)


@router.patch("/{repository_id}", response_model=RepositoryRead)
async def update_repository(
    repository_id: UUID,
    payload: RepositoryUpdate,
    service: CatalogService = Depends(get_catalog_service),
) -> RepositoryRead:
    repository = await service.update_repository(
        repository_id, payload.model_dump(exclude_unset=True)
    )
    if repository is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return RepositoryRead.model_validate(repository)


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> Response:
    if not await service.delete_repository(repository_id):
        raise HTTPException(status_code=404, detail="Repository not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
