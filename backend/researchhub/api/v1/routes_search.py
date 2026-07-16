"""Search endpoints backed by PostgreSQL full-text search."""

from fastapi import APIRouter, Depends, HTTPException, Query

from researchhub.api.v1.dependencies import (
    get_search_service,
    get_semantic_search_service,
    require_permission,
)
from researchhub.api.v1.routes_publications import publication_response
from researchhub.application.services import SearchService, SemanticSearchService
from researchhub.core.permissions import Permissions
from researchhub.domain.schemas import (
    PublicationRead,
    SearchQuery,
    SemanticSearchResponse,
    SemanticSearchResult,
)

router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_permission(Permissions.PUBLICATIONS_READ))],
)


@router.get("/publications", response_model=list[PublicationRead])
async def search_publications(
    q: str | None = None,
    author: str | None = None,
    keyword: str | None = None,
    journal: str | None = None,
    year: int | None = None,
    language: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: SearchService = Depends(get_search_service),
) -> list[PublicationRead]:
    """Search publications by title text and normalized facets."""

    query = SearchQuery(
        q=q,
        author=author,
        keyword=keyword,
        journal=journal,
        year=year,
        language=language,
        limit=limit,
        offset=offset,
    )
    publications = await service.search_publications(query)
    return [publication_response(item) for item in publications]


@router.get("/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
    q: str = Query(min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    source: str | None = None,
    min_similarity: float | None = Query(default=None, ge=0, le=1),
    service: SemanticSearchService = Depends(get_semantic_search_service),
) -> SemanticSearchResponse:
    """Search embedded active publications using pgvector cosine similarity."""

    try:
        results = await service.search(
            q,
            limit=limit,
            source=source,
            min_similarity=min_similarity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SemanticSearchResponse(
        query=q.strip(),
        model=service.encoder.get_model_name(),
        count=len(results),
        results=[SemanticSearchResult.model_validate(item) for item in results],
        ranking_strategy="hybrid",
        warnings=(
            ["Vector search was unavailable or had no matches; lexical fallback was used."]
            if results and all(not item.get("semantic_score") for item in results)
            else []
        ),
    )
