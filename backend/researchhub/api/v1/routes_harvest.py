"""Harvest job endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from researchhub.api.v1.dependencies import (
    get_connector_service,
    get_harvest_operations_service,
    require_permission,
)
from researchhub.application.harvest_operations import HarvestOperationsService
from researchhub.application.services import ConnectorService
from researchhub.application.worker import run_source_harvest
from researchhub.core.permissions import Permissions
from researchhub.domain.schemas import (
    HarvestEventRead,
    HarvestFailureRead,
    HarvestJobDetail,
    HarvestJobRead,
    HarvestRequest,
)

router = APIRouter(
    prefix="/harvest",
    tags=["harvest"],
    dependencies=[Depends(require_permission(Permissions.SOURCES_READ))],
)


@router.post(
    "/jobs", response_model=HarvestJobRead, status_code=202,
    dependencies=[Depends(require_permission(Permissions.HARVEST_START))],
)
async def queue_harvest(
    payload: HarvestRequest,
    service: ConnectorService = Depends(get_connector_service),
) -> HarvestJobRead:
    """Queue a harvest job for asynchronous worker execution."""

    job = await service.queue_harvest(payload)
    return HarvestJobRead.model_validate(job)


@router.get("/jobs", response_model=list[HarvestJobDetail])
async def list_harvest_jobs(
    source_id: UUID | None = None,
    job_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    service: HarvestOperationsService = Depends(get_harvest_operations_service),
) -> list[HarvestJobDetail]:
    return [
        HarvestJobDetail.model_validate(item)
        for item in await service.list(source_id=source_id, status=job_status, limit=limit)
    ]


@router.get("/jobs/{job_id}", response_model=HarvestJobDetail)
async def get_harvest_job(
    job_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> HarvestJobDetail:
    item = await service.get(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Harvest job not found")
    return HarvestJobDetail.model_validate(item)


@router.post(
    "/jobs/{job_id}/cancel", response_model=HarvestJobDetail,
    dependencies=[Depends(require_permission(Permissions.HARVEST_CANCEL))],
)
async def cancel_harvest_job(
    job_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> HarvestJobDetail:
    try:
        return HarvestJobDetail.model_validate(await service.cancel(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def _retry(
    job_id: UUID, service: HarvestOperationsService, failed_only: bool = False
) -> HarvestJobDetail:
    try:
        job = await service.retry(job_id, failed_only=failed_only)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    run_source_harvest.delay(str(job.id))
    return HarvestJobDetail.model_validate(job)


@router.post(
    "/jobs/{job_id}/retry", response_model=HarvestJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(Permissions.HARVEST_START))],
)
async def retry_harvest_job(
    job_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> HarvestJobDetail:
    return await _retry(job_id, service)


@router.post(
    "/jobs/{job_id}/retry-failed",
    response_model=HarvestJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(Permissions.HARVEST_START))],
)
async def retry_failed_harvest(
    job_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> HarvestJobDetail:
    return await _retry(job_id, service, True)


@router.post(
    "/jobs/{job_id}/resume", response_model=HarvestJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permission(Permissions.HARVEST_START))],
)
async def resume_harvest_job(
    job_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> HarvestJobDetail:
    return await _retry(job_id, service)


@router.get("/jobs/{job_id}/events", response_model=list[HarvestEventRead])
async def harvest_job_events(
    job_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> list[HarvestEventRead]:
    try:
        return [HarvestEventRead.model_validate(item) for item in await service.events(job_id)]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/failures", response_model=list[HarvestFailureRead])
async def harvest_job_failures(
    job_id: UUID, service: HarvestOperationsService = Depends(get_harvest_operations_service)
) -> list[HarvestFailureRead]:
    try:
        return [HarvestFailureRead.model_validate(item) for item in await service.failures(job_id)]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
