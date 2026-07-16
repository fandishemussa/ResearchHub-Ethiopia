"""Indexed research-document metadata, chunks, and secure PDF content."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from researchhub.api.v1.dependencies import get_research_document_service, require_permission
from researchhub.application.documents import ResearchDocumentService
from researchhub.core.permissions import Permissions
from researchhub.domain.schemas import (
    DocumentChunkPage,
    DocumentChunkRead,
    ResearchDocumentPage,
    ResearchDocumentRead,
)

router = APIRouter(
    prefix="/documents",
    tags=["research-documents"],
    dependencies=[Depends(require_permission(Permissions.DOCUMENTS_READ))],
)


@router.get("", response_model=ResearchDocumentPage)
async def list_documents(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None, max_length=50),
    document_status: str | None = Query(default=None, alias="status", max_length=30),
    search: str | None = Query(default=None, max_length=255),
    service: ResearchDocumentService = Depends(get_research_document_service),
) -> ResearchDocumentPage:
    items, total = await service.list_documents(
        limit=limit, offset=offset, source=source, status=document_status, search=search
    )
    return ResearchDocumentPage(
        items=[ResearchDocumentRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=ResearchDocumentRead)
async def get_document(
    document_id: UUID, service: ResearchDocumentService = Depends(get_research_document_service)
) -> ResearchDocumentRead:
    item = await service.get(document_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Research document not found")
    return ResearchDocumentRead.model_validate(item)


@router.get("/{document_id}/chunks", response_model=DocumentChunkPage)
async def list_document_chunks(
    document_id: UUID,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=500),
    page: int | None = Query(default=None, ge=1, le=100_000),
    section: str | None = Query(default=None, max_length=255),
    content_type: str | None = Query(default=None, max_length=80),
    service: ResearchDocumentService = Depends(get_research_document_service),
) -> DocumentChunkPage:
    try:
        items, total = await service.chunks(
            document_id,
            limit=limit,
            offset=offset,
            search=search,
            page=page,
            section=section,
            content_type=content_type,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DocumentChunkPage(
        items=[DocumentChunkRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}/content",
    response_class=FileResponse,
    dependencies=[Depends(require_permission(Permissions.DOCUMENTS_DOWNLOAD))],
)
async def document_content(
    document_id: UUID,
    page: int | None = Query(default=None, ge=1, le=100_000),
    service: ResearchDocumentService = Depends(get_research_document_service),
) -> FileResponse:
    del page
    try:
        path = await service.content_path(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="research-document.pdf",
        content_disposition_type="inline",
    )
