"""Validated XML, JSON, and CSV metadata import endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from researchhub.api.v1.dependencies import get_import_operations_service
from researchhub.application.import_operations import ImportOperationsService
from researchhub.domain.schemas import HarvestJobDetail

router = APIRouter(prefix="/import", tags=["metadata-imports"])


async def _upload(
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


@router.post("/xml", response_model=HarvestJobDetail, status_code=status.HTTP_201_CREATED)
async def upload_xml(
    source_id: UUID = Form(),
    file: UploadFile = File(),
    service: ImportOperationsService = Depends(get_import_operations_service),
) -> HarvestJobDetail:
    return await _upload(source_id, "xml", file, service)


@router.post("/json", response_model=HarvestJobDetail, status_code=status.HTTP_201_CREATED)
async def upload_json(
    source_id: UUID = Form(),
    file: UploadFile = File(),
    service: ImportOperationsService = Depends(get_import_operations_service),
) -> HarvestJobDetail:
    return await _upload(source_id, "json", file, service)


@router.post("/csv", response_model=HarvestJobDetail, status_code=status.HTTP_201_CREATED)
async def upload_csv(
    source_id: UUID = Form(),
    file: UploadFile = File(),
    service: ImportOperationsService = Depends(get_import_operations_service),
) -> HarvestJobDetail:
    return await _upload(source_id, "csv", file, service)


@router.post("/{job_id}/preview")
async def preview_import(
    job_id: UUID, service: ImportOperationsService = Depends(get_import_operations_service)
) -> dict:
    try:
        return await service.preview(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{job_id}/confirm", response_model=HarvestJobDetail)
async def confirm_import(
    job_id: UUID, service: ImportOperationsService = Depends(get_import_operations_service)
) -> HarvestJobDetail:
    try:
        return HarvestJobDetail.model_validate(await service.confirm(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/cancel", response_model=HarvestJobDetail)
async def cancel_import(
    job_id: UUID, service: ImportOperationsService = Depends(get_import_operations_service)
) -> HarvestJobDetail:
    try:
        return HarvestJobDetail.model_validate(await service.cancel(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
