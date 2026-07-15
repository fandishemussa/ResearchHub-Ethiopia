"""FastAPI dependency providers for application services."""

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from researchhub_ai.chat import FallbackChatProvider, GroundedLLMProvider, GroundedLocalProvider
from researchhub_ai.embeddings import get_embedding_service
from researchhub_ai.providers import create_ai_provider
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.application.auth import AuthenticationError, AuthenticationService
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
    if provider_name == "local":
        chat_provider = GroundedLocalProvider()
    else:
        ai_provider = create_ai_provider(
            provider_name,
            embedding_model=settings.embedding_model,
            device=settings.embedding_device,
            chat_model=settings.ai_chat_model,
            timeout=settings.ai_request_timeout,
            ollama_base_url=str(settings.ollama_base_url),
            openai_base_url=str(settings.openai_base_url) if settings.openai_base_url else None,
            openai_api_key=settings.openai_api_key,
        )
        chat_provider = FallbackChatProvider(
            GroundedLLMProvider(
                ai_provider,
                model=settings.ai_chat_model,
                max_context_chars=max(8000, settings.ai_chat_max_context_tokens * 4),
            ),
            GroundedLocalProvider(),
        )
    return ResearchChatService(
        session,
        chat_provider,
        max_sources=min(settings.ai_chat_retrieval_limit, 16),
    )


def get_research_document_service(
    session: AsyncSession = Depends(get_db_session),
) -> ResearchDocumentService:
    return ResearchDocumentService(session)


def get_research_intelligence_service(
    session: AsyncSession = Depends(get_db_session),
) -> ResearchIntelligenceService:
    return ResearchIntelligenceService(session)


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
