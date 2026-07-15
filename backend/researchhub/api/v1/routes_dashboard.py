"""Dashboard and statistics endpoints for institutional reporting."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from researchhub.api.v1.dependencies import get_analytics_service
from researchhub.application.services import AnalyticsService

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
statistics_router = APIRouter(prefix="/statistics", tags=["statistics"])


@dashboard_router.get("/summary")
async def dashboard_summary(
    service: AnalyticsService = Depends(get_analytics_service),
) -> dict[str, Any]:
    """Return dashboard summary cards and managed-source health."""

    counts = await service.publication_counts()
    sources = await service.source_status()
    return {"counts": counts, "source_status": sources}


@dashboard_router.get("/publication-trends")
async def publication_trends(
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[dict[str, Any]]:
    """Return annual publication growth for dashboards."""

    return await service.publication_trends()


@dashboard_router.get("/keyword-trends")
async def keyword_trends(
    limit: int = Query(default=25, ge=1, le=100),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[dict[str, Any]]:
    """Return keyword frequency trends."""

    return await service.keyword_trends(limit=limit)


@statistics_router.get("/publications")
async def publication_statistics(
    service: AnalyticsService = Depends(get_analytics_service),
) -> dict[str, Any]:
    """Return publication statistics for reports and dashboards."""

    return await service.publication_counts()
