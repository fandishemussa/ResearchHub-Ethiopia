"""Public AI research-intelligence endpoints."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse

from researchhub.api.v1.dependencies import (
    get_publication_similarity_service,
    get_research_chat_service,
    get_research_intelligence_service,
)
from researchhub.application.chatbot import (
    ResearchChatService,
    follow_up_questions,
    grounding_status,
)
from researchhub.application.research_intelligence import ResearchIntelligenceService
from researchhub.application.services import PublicationSimilarityService
from researchhub.domain.schemas import (
    AIKeywordRead,
    ChatFeedbackCreate,
    ChatMessageRead,
    ChatQuery,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionRead,
    ChatSessionUpdate,
    CitationRead,
    DuplicateCandidateRead,
    PublicationSimilarityResponse,
    SimilarPublicationResult,
    SummaryRead,
    SummaryRequest,
    TrendOverviewPoint,
)

router = APIRouter(prefix="/ai", tags=["ai-research-intelligence"])


@router.get(
    "/publications/{publication_id}/similar",
    response_model=PublicationSimilarityResponse,
)
async def similar_publications(
    publication_id: UUID,
    limit: int = Query(default=10, ge=1, le=50),
    minimum_score: float | None = Query(default=None, ge=0, le=1),
    university_id: UUID | None = None,
    year_from: int | None = Query(default=None, ge=1800, le=3000),
    year_to: int | None = Query(default=None, ge=1800, le=3000),
    publication_type: str | None = Query(default=None, max_length=120),
    service: PublicationSimilarityService = Depends(get_publication_similarity_service),
) -> PublicationSimilarityResponse:
    """Return active embedded publications similar to a selected publication."""

    try:
        target, results = await service.similar(
            publication_id,
            limit=limit,
            minimum_score=minimum_score,
            university_id=university_id,
            year_from=year_from,
            year_to=year_to,
            publication_type=publication_type,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PublicationSimilarityResponse(
        publication_id=target.id,
        model=target.embedding_model or "unknown",
        count=len(results),
        results=[SimilarPublicationResult.model_validate(item) for item in results],
    )


@router.post("/chat/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    payload: ChatSessionCreate,
    service: ResearchChatService = Depends(get_research_chat_service),
) -> ChatSessionRead:
    return ChatSessionRead.model_validate(
        await service.create_session(university_id=payload.university_id, title=payload.title)
    )


@router.get("/chat/sessions", response_model=list[ChatSessionRead])
async def list_chat_sessions(
    service: ResearchChatService = Depends(get_research_chat_service),
) -> list[ChatSessionRead]:
    return [ChatSessionRead.model_validate(item) for item in await service.list_sessions()]


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionRead)
async def get_chat_session(
    session_id: UUID,
    service: ResearchChatService = Depends(get_research_chat_service),
) -> ChatSessionRead:
    item = await service.get_session(session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return ChatSessionRead.model_validate(item)


@router.delete("/chat/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    session_id: UUID,
    service: ResearchChatService = Depends(get_research_chat_service),
) -> Response:
    if not await service.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Chat session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/chat/sessions/{session_id}", response_model=ChatSessionRead)
async def update_chat_session(
    session_id: UUID,
    payload: ChatSessionUpdate,
    service: ResearchChatService = Depends(get_research_chat_service),
) -> ChatSessionRead:
    try:
        item = await service.update_session(
            session_id,
            title=payload.title,
            is_pinned=payload.is_pinned,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatSessionRead.model_validate(item)


@router.get("/chat/sessions/{session_id}/messages", response_model=list[ChatMessageRead])
async def list_chat_messages(
    session_id: UUID,
    service: ResearchChatService = Depends(get_research_chat_service),
) -> list[ChatMessageRead]:
    item = await service.get_session(session_id, with_messages=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return [ChatMessageRead.model_validate(message) for message in item.messages]


@router.post("/chat/query", response_model=ChatResponse)
@router.post("/chat/sessions/{path_session_id}/messages", response_model=ChatResponse)
async def ask_research_chatbot(
    payload: ChatQuery,
    path_session_id: UUID | None = None,
    service: ResearchChatService = Depends(get_research_chat_service),
) -> ChatResponse:
    if payload.stream:
        raise HTTPException(
            status_code=501, detail="Streaming is not available with the local provider yet"
        )
    try:
        session, message = await service.ask(
            payload.message,
            session_id=path_session_id or payload.session_id,
            university_id=payload.university_id,
            university_ids=payload.filters.universities or None,
            year_from=payload.filters.year_from or payload.year_from,
            year_to=payload.filters.year_to or payload.year_to,
            publication_ids=payload.publication_ids or None,
            document_ids=payload.document_ids or None,
            pinned_chunk_ids=payload.pinned_chunk_ids or None,
            repository_sources=payload.filters.repositories or None,
            document_types=payload.filters.document_types or None,
            languages=payload.filters.languages or None,
            minimum_similarity=payload.filters.minimum_similarity,
            top_documents=payload.retrieval.top_documents,
            top_chunks=payload.retrieval.top_chunks,
            include_full_text=payload.retrieval.include_full_text,
            include_metadata=payload.retrieval.include_metadata,
            mode=payload.mode,
            answer_length=payload.retrieval.answer_length,
            response_language=payload.retrieval.response_language,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    retrieved_document_count = len(
        {
            citation.get("document_id")
            for citation in message.citations
            if citation.get("document_id")
        }
    )
    retrieved_chunk_count = sum(
        citation.get("source_type") == "document_chunk" for citation in message.citations
    )
    grounding = grounding_status(message.citations)
    return ChatResponse(
        session_id=session.id,
        message_id=message.id,
        answer=message.content,
        citations=message.citations,
        retrieved_publications=message.retrieved_publication_ids,
        confidence=0.75 if message.citations else 0.0,
        model=message.model_name or "unknown",
        latency_ms=message.latency_ms,
        usage=message.usage,
        warnings=message.warnings,
        retrieved_document_count=retrieved_document_count,
        retrieved_chunk_count=retrieved_chunk_count,
        grounding_status=grounding,
        model_name=message.model_name or "unknown",
        follow_up_questions=follow_up_questions(payload.mode, grounding),
    )


@router.get("/documents/{document_id}/view", response_class=FileResponse)
async def view_research_document(
    document_id: UUID,
    page: int | None = Query(default=None, ge=1, le=100_000),
    service: ResearchChatService = Depends(get_research_chat_service),
) -> FileResponse:
    """Serve an indexed PDF without exposing its local filesystem path."""

    del page  # Browser PDF viewers may use the requested page client-side.
    try:
        path = await service.document_preview_path(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="research-document.pdf",
        content_disposition_type="inline",
    )


@router.post("/chat/feedback", status_code=status.HTTP_201_CREATED)
async def submit_chat_feedback(
    payload: ChatFeedbackCreate,
    service: ResearchChatService = Depends(get_research_chat_service),
) -> dict[str, str]:
    try:
        feedback = await service.add_feedback(payload.message_id, payload.rating, payload.comment)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": str(feedback.id), "status": "recorded"}


@router.post("/publications/{publication_id}/summarize", response_model=SummaryRead)
async def summarize_publication(
    publication_id: UUID,
    payload: SummaryRequest,
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> SummaryRead:
    try:
        result = await service.summarize(
            publication_id, payload.summary_type, payload.max_length, payload.force_regenerate
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SummaryRead.model_validate(result)


@router.get("/publications/{publication_id}/summary", response_model=SummaryRead | None)
async def latest_publication_summary(
    publication_id: UUID,
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> SummaryRead | None:
    try:
        items = await service.summaries(publication_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SummaryRead.model_validate(items[0]) if items else None


@router.get("/publications/{publication_id}/summaries", response_model=list[SummaryRead])
async def list_publication_summaries(
    publication_id: UUID,
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> list[SummaryRead]:
    try:
        return [
            SummaryRead.model_validate(item) for item in await service.summaries(publication_id)
        ]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/publications/{publication_id}/extract-keywords", response_model=list[AIKeywordRead])
async def extract_publication_keywords(
    publication_id: UUID,
    limit: int = Query(default=10, ge=1, le=30),
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> list[AIKeywordRead]:
    try:
        return [
            AIKeywordRead.model_validate(item)
            for item in await service.keywords(publication_id, limit)
        ]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/publications/{publication_id}/citation", response_model=CitationRead)
async def generate_publication_citation(
    publication_id: UUID,
    style: str = Query(default="apa7", max_length=40),
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> CitationRead:
    try:
        return CitationRead.model_validate(await service.citation(publication_id, style.casefold()))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/trends/overview", response_model=list[TrendOverviewPoint])
async def research_trend_overview(
    year_from: int | None = Query(default=None, ge=1800, le=3000),
    year_to: int | None = Query(default=None, ge=1800, le=3000),
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> list[TrendOverviewPoint]:
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(
            status_code=422, detail="year_from must be less than or equal to year_to"
        )
    return [
        TrendOverviewPoint.model_validate(item)
        for item in await service.trend_overview(year_from, year_to)
    ]


@router.post(
    "/duplicates/publication/{publication_id}", response_model=list[DuplicateCandidateRead]
)
async def scan_publication_duplicates(
    publication_id: UUID,
    threshold: float = Query(default=0.65, ge=0, le=1),
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> list[DuplicateCandidateRead]:
    try:
        return [
            DuplicateCandidateRead.model_validate(item)
            for item in await service.scan_duplicates(publication_id, threshold)
        ]
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/duplicates", response_model=list[DuplicateCandidateRead])
async def list_duplicate_candidates(
    candidate_status: str | None = Query(default=None, alias="status", max_length=40),
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> list[DuplicateCandidateRead]:
    return [
        DuplicateCandidateRead.model_validate(item)
        for item in await service.duplicate_candidates(candidate_status)
    ]


@router.post("/duplicates/{candidate_id}/{action}", response_model=DuplicateCandidateRead)
async def review_duplicate_candidate(
    candidate_id: UUID,
    action: Literal["confirm", "reject", "ignore"],
    service: ResearchIntelligenceService = Depends(get_research_intelligence_service),
) -> DuplicateCandidateRead:
    statuses = {"confirm": "confirmed_duplicate", "reject": "not_duplicate", "ignore": "ignored"}
    try:
        return DuplicateCandidateRead.model_validate(
            await service.review_duplicate(candidate_id, statuses[action])
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
