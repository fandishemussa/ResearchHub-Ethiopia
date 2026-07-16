"""Administrative source management and health endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status

from researchhub.api.v1.dependencies import (
    get_harvest_operations_service,
    get_import_operations_service,
    get_source_management_service,
    require_permission,
)
from researchhub.application.harvest_operations import HarvestOperationsService
from researchhub.application.import_operations import ImportOperationsService
from researchhub.application.source_management import (
    SourceManagementService,
    test_source_configuration,
)
from researchhub.application.worker import run_source_harvest
from researchhub.core.permissions import Permissions
from researchhub.domain.schemas import (
    HarvestJobDetail,
    HarvestJobRead,
    SourceConnectionTestRequest,
    SourceConnectionTestResult,
    SourceCreate,
    SourceHarvestRequest,
    SourceRead,
    SourceUpdate,
)

router = APIRouter(
    prefix="/sources",
    tags=["source-management"],
    dependencies=[Depends(require_permission(Permissions.SOURCES_READ))],
)


@router.get("", response_model=list[SourceRead])
async def list_sources(
    source_type: str | None = None,
    source_status: str | None = Query(default=None, alias="status"),
    university_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: SourceManagementService = Depends(get_source_management_service),
) -> list[SourceRead]:
    return [
        SourceRead.model_validate(item)
        for item in await service.list(
            source_type=source_type,
            status=source_status,
            university_id=university_id,
            limit=limit,
            offset=offset,
        )
    ]


@router.post(
    "/test-configuration",
    response_model=SourceConnectionTestResult,
    dependencies=[Depends(require_permission(Permissions.SOURCES_MANAGE))],
)
async def test_unsaved_source(payload: SourceConnectionTestRequest) -> SourceConnectionTestResult:
    result = await test_source_configuration(
        payload.source_type,
        payload.slug,
        payload.name,
        str(payload.oai_endpoint or payload.api_url or payload.base_url)
        if payload.oai_endpoint or payload.api_url or payload.base_url
        else None,
        payload.metadata_prefix,
        payload.set_spec,
    )
    return SourceConnectionTestResult.model_validate(result)


@router.post(
    "",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permissions.SOURCES_MANAGE))],
)
async def create_source(
    payload: SourceCreate, service: SourceManagementService = Depends(get_source_management_service)
) -> SourceRead:
    try:
        return SourceRead.model_validate(await service.create(payload))
    except ValueError as exc:
        raise HTTPException(
            status_code=409 if "already exists" in str(exc) else 422, detail=str(exc)
        ) from exc


@router.get("/{source_id}", response_model=SourceRead)
async def get_source(
    source_id: UUID, service: SourceManagementService = Depends(get_source_management_service)
) -> SourceRead:
    item = await service.get(source_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceRead.model_validate(item)


@router.patch(
    "/{source_id}", response_model=SourceRead,
    dependencies=[Depends(require_permission(Permissions.SOURCES_MANAGE))],
)
@router.put(
    "/{source_id}", response_model=SourceRead,
    dependencies=[Depends(require_permission(Permissions.SOURCES_MANAGE))],
)
async def update_source(
    source_id: UUID,
    payload: SourceUpdate,
    service: SourceManagementService = Depends(get_source_management_service),
) -> SourceRead:
    try:
        return SourceRead.model_validate(await service.update(source_id, payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409 if "already exists" in str(exc) else 422,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{source_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permissions.SOURCES_MANAGE))],
)
async def delete_source(
    source_id: UUID, service: SourceManagementService = Depends(get_source_management_service)
) -> Response:
    try:
        if not await service.delete(source_id):
            raise HTTPException(status_code=404, detail="Source not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{source_id}/enable", response_model=SourceRead,
    dependencies=[Depends(require_permission(Permissions.SOURCES_MANAGE))],
)
async def enable_source(
    source_id: UUID, service: SourceManagementService = Depends(get_source_management_service)
) -> SourceRead:
    try:
        return SourceRead.model_validate(await service.set_enabled(source_id, True))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{source_id}/disable", response_model=SourceRead,
    dependencies=[Depends(require_permission(Permissions.SOURCES_MANAGE))],
)
async def disable_source(
    source_id: UUID, service: SourceManagementService = Depends(get_source_management_service)
) -> SourceRead:
    try:
        return SourceRead.model_validate(await service.set_enabled(source_id, False))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{source_id}/test", response_model=SourceConnectionTestResult,
    dependencies=[Depends(require_permission(Permissions.SOURCES_MANAGE))],
)
async def test_source(
    source_id: UUID, service: SourceManagementService = Depends(get_source_management_service)
) -> SourceConnectionTestResult:
    try:
        return SourceConnectionTestResult.model_validate(await service.test_saved(source_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{source_id}/health", response_model=SourceRead)
async def source_health(
    source_id: UUID, service: SourceManagementService = Depends(get_source_management_service)
) -> SourceRead:
    return await get_source(source_id, service)


@router.get("/{source_id}/statistics")
async def source_statistics(
    source_id: UUID, service: SourceManagementService = Depends(get_source_management_service)
) -> dict[str, int]:
    try:
        return await service.statistics(source_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{source_id}/harvest-history", response_model=list[HarvestJobRead])
async def source_history(
    source_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    service: SourceManagementService = Depends(get_source_management_service),
) -> list[HarvestJobRead]:
    try:
        return [
            HarvestJobRead.model_validate(item) for item in await service.history(source_id, limit)
        ]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _queue_harvest(
    source_id: UUID, payload: SourceHarvestRequest, service: HarvestOperationsService
) -> HarvestJobDetail:
    try:
        job = await service.queue(source_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run_source_harvest.delay(str(job.id))
    return HarvestJobDetail.model_validate(job)


@router.post(
    "/{source_id}/harvest", response_model=HarvestJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(Permissions.HARVEST_START))],
)
async def run_source(
    source_id: UUID,
    payload: SourceHarvestRequest,
    service: HarvestOperationsService = Depends(get_harvest_operations_service),
) -> HarvestJobDetail:
    return await _queue_harvest(source_id, payload, service)


@router.post(
    "/{source_id}/harvest/full",
    response_model=HarvestJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(Permissions.HARVEST_START))],
)
async def run_full_source(
    source_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> HarvestJobDetail:
    return await _queue_harvest(source_id, SourceHarvestRequest(mode="full"), service)


@router.post(
    "/{source_id}/harvest/incremental",
    response_model=HarvestJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(Permissions.HARVEST_START))],
)
async def run_incremental_source(
    source_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> HarvestJobDetail:
    return await _queue_harvest(source_id, SourceHarvestRequest(mode="incremental"), service)


@router.post(
    "/{source_id}/harvest/dry-run",
    response_model=HarvestJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(Permissions.HARVEST_START))],
)
async def run_dry_source(
    source_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> HarvestJobDetail:
    return await _queue_harvest(
        source_id,
        SourceHarvestRequest(mode="dry_run", dry_run=True, import_to_database=False),
        service,
    )


async def _source_upload(
    source_id: UUID, file_format: str, file: UploadFile, service: ImportOperationsService
) -> HarvestJobDetail:
    try:
        job = await service.upload(
            source_id,
            file_format,
            file.filename or f"upload.{file_format}",
            file.content_type or "application/octet-stream",
            await file.read(),
        )
        return HarvestJobDetail.model_validate(job)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{source_id}/import/xml", response_model=HarvestJobDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permissions.IMPORTS_CREATE))],
)
async def source_import_xml(
    source_id: UUID,
    file: UploadFile = File(),
    service: ImportOperationsService = Depends(get_import_operations_service),
) -> HarvestJobDetail:
    return await _source_upload(source_id, "xml", file, service)


@router.post(
    "/{source_id}/import/json", response_model=HarvestJobDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permissions.IMPORTS_CREATE))],
)
async def source_import_json(
    source_id: UUID,
    file: UploadFile = File(),
    service: ImportOperationsService = Depends(get_import_operations_service),
) -> HarvestJobDetail:
    return await _source_upload(source_id, "json", file, service)


@router.post(
    "/{source_id}/import/csv", response_model=HarvestJobDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permissions.IMPORTS_CREATE))],
)
async def source_import_csv(
    source_id: UUID,
    file: UploadFile = File(),
    service: ImportOperationsService = Depends(get_import_operations_service),
) -> HarvestJobDetail:
    return await _source_upload(source_id, "csv", file, service)
