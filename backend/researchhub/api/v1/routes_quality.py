"""Metadata quality assessment endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from researchhub.api.v1.dependencies import get_quality_service
from researchhub.application.metadata_quality import MetadataQualityService
from researchhub.domain.schemas import (
    QualityIssuePage,
    QualityIssueRead,
    QualityRecalculateAllRead,
    QualityReportPage,
    QualityReportRead,
    QualitySummaryRead,
)
from researchhub.infrastructure.persistence.repositories import QualityReportFilters

router = APIRouter(prefix="/quality", tags=["quality"])


def _quality_filters(
    grade: str | None = Query(default=None, min_length=1, max_length=1),
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    issue_type: str | None = Query(default=None),
    university_id: UUID | None = Query(default=None),
    repository_id: UUID | None = Query(default=None),
    journal_id: UUID | None = Query(default=None),
    year: int | None = Query(default=None, ge=1800, le=3000),
    is_deleted: bool | None = Query(default=False),
    include_deleted: bool = Query(default=False),
    sort_by: str = Query(default="assessed_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> QualityReportFilters:
    """Map shared quality query parameters to repository filters."""

    return QualityReportFilters(
        grade=grade.upper() if grade else None,
        min_score=min_score,
        max_score=max_score,
        issue_type=issue_type,
        university_id=university_id,
        repository_id=repository_id,
        journal_id=journal_id,
        year=year,
        is_deleted=None if include_deleted else is_deleted,
        sort_by=sort_by,
        sort_order=sort_order,
    )


def _report_page_response(page) -> QualityReportPage:
    """Convert a repository page to the public response schema."""

    return QualityReportPage(
        items=[QualityReportRead.model_validate(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/reports", response_model=list[QualityReportRead])
async def latest_quality_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    filters: QualityReportFilters = Depends(_quality_filters),
    service: MetadataQualityService = Depends(get_quality_service),
) -> list[QualityReportRead]:
    """List latest metadata quality reports.

    This preserves the original lightweight route shape for early clients.
    Use ``/quality/low-quality`` and ``/quality/issues`` for paginated pages.
    """

    page = await service.latest_reports(filters, limit=limit, offset=offset)
    return [QualityReportRead.model_validate(item) for item in page.items]


@router.get("/publications/{publication_id}", response_model=QualityReportRead)
async def publication_quality_report(
    publication_id: UUID,
    service: MetadataQualityService = Depends(get_quality_service),
) -> QualityReportRead:
    """Return the current quality report for one publication."""

    report = await service.get_publication_report(publication_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "quality_report_not_found", "message": "No quality report exists."},
        )
    return QualityReportRead.model_validate(report)


@router.get("/summary", response_model=QualitySummaryRead)
async def quality_summary(
    filters: QualityReportFilters = Depends(_quality_filters),
    service: MetadataQualityService = Depends(get_quality_service),
) -> QualitySummaryRead:
    """Return aggregate metadata quality metrics."""

    summary = await service.summary(filters)
    return QualitySummaryRead.model_validate(summary)


@router.get("/issues", response_model=QualityIssuePage)
async def quality_issues(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    filters: QualityReportFilters = Depends(_quality_filters),
    service: MetadataQualityService = Depends(get_quality_service),
) -> QualityIssuePage:
    """List flattened metadata quality issues."""

    page = await service.issues(filters, limit=limit, offset=offset)
    return QualityIssuePage(
        items=[QualityIssueRead.model_validate(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/low-quality", response_model=QualityReportPage)
async def low_quality_publications(
    threshold: float = Query(default=70.0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    filters: QualityReportFilters = Depends(_quality_filters),
    service: MetadataQualityService = Depends(get_quality_service),
) -> QualityReportPage:
    """List publications whose current quality score is below the threshold."""

    page = await service.low_quality_reports(
        filters,
        threshold=threshold,
        limit=limit,
        offset=offset,
    )
    return _report_page_response(page)


@router.post("/publications/{publication_id}/recalculate", response_model=QualityReportRead)
async def recalculate_publication_quality(
    publication_id: UUID,
    service: MetadataQualityService = Depends(get_quality_service),
) -> QualityReportRead:
    """Recalculate and persist the quality report for one publication."""

    report = await service.recalculate_publication(publication_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "publication_not_found", "message": "Publication was not found."},
        )
    return QualityReportRead.model_validate(report)


@router.post("/recalculate-all", response_model=QualityRecalculateAllRead)
async def recalculate_all_quality(
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: MetadataQualityService = Depends(get_quality_service),
) -> QualityRecalculateAllRead:
    """Recalculate quality for a bounded batch of publications."""

    result = await service.recalculate_all(
        is_deleted=None if include_deleted else False,
        limit=limit,
        offset=offset,
    )
    return QualityRecalculateAllRead.model_validate(result)
