"""FastAPI dependency providers for application services."""

from collections.abc import AsyncIterator, Callable, Collection
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from researchhub_ai.chat import (
    ChatProvider,
    FallbackChatProvider,
    GroundedLLMProvider,
    GroundedLocalProvider,
)
from researchhub_ai.context import ContextManager, ContextPolicy
from researchhub_ai.embeddings import get_embedding_service
from researchhub_ai.providers import create_ai_provider
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.application.auth import AuthenticationError, AuthenticationService
from researchhub.application.authorization import AuthorizationService
from researchhub.application.chatbot import ResearchChatService
from researchhub.application.documents import ResearchDocumentService
from researchhub.application.harvest_operations import HarvestOperationsService
from researchhub.application.import_operations import ImportOperationsService
from researchhub.application.metadata_quality import MetadataQualityService
from researchhub.application.research_intelligence import ResearchIntelligenceService
from researchhub.application.services import (
    AnalyticsService,
    CatalogService,
    ConnectorService,
    PublicationService,
    PublicationSimilarityService,
    SearchService,
    SemanticSearchService,
)
from researchhub.application.source_management import SourceManagementService
from researchhub.core.config import get_settings
from researchhub.infrastructure.persistence.models import User
from researchhub.infrastructure.persistence.session import get_session


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


def get_catalog_service(session: AsyncSession = Depends(get_db_session)) -> CatalogService:
    return CatalogService(session)


def get_publication_service(session: AsyncSession = Depends(get_db_session)) -> PublicationService:
    return PublicationService(session)


def get_search_service(session: AsyncSession = Depends(get_db_session)) -> SearchService:
    return SearchService(session)


def get_semantic_search_service(
    session: AsyncSession = Depends(get_db_session),
) -> SemanticSearchService:
    settings = get_settings()
    encoder = get_embedding_service(settings.embedding_model, settings.embedding_device)
    return SemanticSearchService(session, encoder)


def get_publication_similarity_service(
    session: AsyncSession = Depends(get_db_session),
) -> PublicationSimilarityService:
    return PublicationSimilarityService(session)


def get_research_chat_service(
    session: AsyncSession = Depends(get_db_session),
) -> ResearchChatService:
    settings = get_settings()
    provider_name = settings.ai_chat_provider.casefold().strip()
    chat_provider: ChatProvider
    if provider_name == "local":
        chat_provider = GroundedLocalProvider()
    else:
        ai_provider = create_ai_provider(
            provider_name,
            embedding_model=settings.embedding_model,
            device=settings.embedding_device,
            chat_model=settings.ollama_model
            if provider_name == "ollama"
            else settings.ai_chat_model,
            timeout=settings.ollama_request_timeout_seconds,
            ollama_base_url=str(settings.ollama_base_url),
            openai_base_url=str(settings.openai_base_url) if settings.openai_base_url else None,
            openai_api_key=settings.openai_api_key,
            ollama_queue_timeout=settings.ollama_queue_timeout_seconds,
            ollama_max_concurrent=settings.ollama_max_concurrent_requests,
            ollama_max_num_ctx=settings.ollama_max_num_ctx,
            ollama_max_num_predict=settings.ollama_max_num_predict,
            ollama_keep_alive=settings.ollama_keep_alive,
            ollama_options={
                "num_ctx": settings.ollama_num_ctx,
                "num_predict": settings.ollama_num_predict,
                "temperature": settings.ollama_temperature,
                "top_p": settings.ollama_top_p,
                "repeat_penalty": settings.ollama_repeat_penalty,
                "num_thread": settings.ollama_num_thread,
            },
        )
        chat_provider = FallbackChatProvider(
            GroundedLLMProvider(
                ai_provider,
                model=settings.ollama_model
                if provider_name == "ollama"
                else settings.ai_chat_model,
                max_context_chars=settings.rag_max_context_tokens * 4,
            ),
            GroundedLocalProvider(),
        )
    context_manager = ContextManager(
        ContextPolicy(
            num_ctx=settings.ollama_num_ctx,
            min_num_ctx=settings.ollama_min_num_ctx,
            max_num_ctx=settings.ollama_max_num_ctx,
            num_predict=settings.ollama_num_predict,
            max_num_predict=settings.ollama_max_num_predict,
            rerank_top_k=settings.rag_rerank_top_k,
            max_chunks=settings.rag_max_context_chunks,
            max_chunk_tokens=settings.rag_max_chunk_tokens,
            target_chunk_tokens=settings.rag_target_chunk_tokens,
            response_reserve=settings.rag_response_token_reserve,
            safety_margin=settings.rag_context_safety_margin,
            min_evidence_tokens=settings.rag_min_evidence_tokens,
            max_context_tokens=settings.rag_max_context_tokens,
            deduplication_threshold=settings.rag_deduplication_threshold,
            adjacent_overlap_threshold=settings.rag_adjacent_chunk_overlap_threshold,
            dynamic_context=settings.rag_enable_dynamic_context,
            compression=settings.rag_enable_context_compression,
            duplicate_removal=settings.rag_enable_duplicate_removal,
            max_history_turns=settings.rag_max_history_turns,
            max_history_tokens=settings.rag_max_history_tokens,
            min_free_memory_mb=settings.ollama_min_free_memory_mb,
            critical_free_memory_mb=settings.ollama_critical_free_memory_mb,
            memory_guard=settings.rag_enable_memory_guard,
        )
    )
    return ResearchChatService(
        session,
        chat_provider,
        max_sources=settings.rag_retrieval_candidates,
        context_manager=context_manager,
        expose_context_diagnostics=(
            settings.rag_expose_context_diagnostics and settings.app_env.casefold() != "production"
        ),
    )


def get_research_intelligence_service(
    session: AsyncSession = Depends(get_db_session),
) -> ResearchIntelligenceService:
    return ResearchIntelligenceService(session)


def get_research_document_service(
    session: AsyncSession = Depends(get_db_session),
) -> ResearchDocumentService:
    return ResearchDocumentService(session)


def get_source_management_service(
    session: AsyncSession = Depends(get_db_session),
) -> SourceManagementService:
    return SourceManagementService(session)


def get_harvest_operations_service(
    session: AsyncSession = Depends(get_db_session),
) -> HarvestOperationsService:
    return HarvestOperationsService(session, get_settings())


def get_import_operations_service(
    session: AsyncSession = Depends(get_db_session),
) -> ImportOperationsService:
    return ImportOperationsService(session, get_settings())


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_authentication_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticationService:
    return AuthenticationService(session, get_settings())


def get_authorization_service(
    session: AsyncSession = Depends(get_db_session),
) -> AuthorizationService:
    return AuthorizationService(session)


async def require_authenticated_user(
    token: str = Depends(oauth2_scheme),
    service: AuthenticationService = Depends(get_authentication_service),
) -> User:
    try:
        return await service.authenticate_access_token(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_permission(code: str) -> Callable[..., object]:
    """Create a fail-closed dependency for one permission code."""

    async def dependency(
        user: User = Depends(require_authenticated_user),
        service: AuthorizationService = Depends(get_authorization_service),
    ) -> User:
        if not await service.has_permission(user.id, code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return dependency


def require_any_permission(codes: Collection[str]) -> Callable[..., object]:
    """Create a dependency that accepts at least one permission code."""

    required = frozenset(codes)

    async def dependency(
        user: User = Depends(require_authenticated_user),
        service: AuthorizationService = Depends(get_authorization_service),
    ) -> User:
        if not await service.has_any_permission(user.id, required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return dependency


async def require_admin_role(
    user: User = Depends(require_authenticated_user),
    service: AuthorizationService = Depends(get_authorization_service),
) -> User:
    if not await service.is_admin(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator required")
    return user


def require_university_scope() -> Callable[..., object]:
    async def dependency(
        university_id: UUID,
        user: User = Depends(require_authenticated_user),
        service: AuthorizationService = Depends(get_authorization_service),
    ) -> User:
        if not await service.within_university(user, university_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="University scope denied")
        return user

    return dependency


def require_department_scope() -> Callable[..., object]:
    async def dependency(
        department_id: UUID,
        user: User = Depends(require_authenticated_user),
        service: AuthorizationService = Depends(get_authorization_service),
    ) -> User:
        if not await service.within_department(user, department_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Department scope denied")
        return user

    return dependency


def get_analytics_service(session: AsyncSession = Depends(get_db_session)) -> AnalyticsService:
    return AnalyticsService(session)


def get_connector_service(session: AsyncSession = Depends(get_db_session)) -> ConnectorService:
    return ConnectorService(session)


def get_quality_service(session: AsyncSession = Depends(get_db_session)) -> MetadataQualityService:
    settings = get_settings()
    return MetadataQualityService(
        session,
        weights=settings.metadata_quality_weights,
        check_url_reachability=settings.metadata_quality_check_url_reachability,
        url_timeout_seconds=settings.metadata_quality_url_timeout_seconds,
    )
