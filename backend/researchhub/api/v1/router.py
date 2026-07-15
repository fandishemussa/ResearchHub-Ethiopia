"""Versioned API router composition."""

from fastapi import APIRouter

from researchhub.api.v1 import (
    routes_ai,
    routes_auth,
    routes_authors,
    routes_harvest,
    routes_documents,
    routes_imports,
    routes_publications,
    routes_quality,
    routes_search,
    routes_sources,
    routes_universities,
)
from researchhub.api.v1.routes_dashboard import dashboard_router, statistics_router

api_router = APIRouter()
api_router.include_router(routes_ai.router)
api_router.include_router(routes_auth.router)
api_router.include_router(routes_universities.router)
api_router.include_router(routes_publications.router)
api_router.include_router(routes_authors.router)
api_router.include_router(routes_search.router)
# `/sources` is the canonical API for editable repository connectors. The older
# repository-catalogue and connector CRUD routes are intentionally not exposed.
api_router.include_router(routes_sources.router)
api_router.include_router(routes_harvest.router)
api_router.include_router(routes_documents.router)
api_router.include_router(routes_imports.router)
api_router.include_router(dashboard_router)
api_router.include_router(statistics_router)
api_router.include_router(routes_quality.router)
