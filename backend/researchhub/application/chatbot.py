"""Grounded, university-scoped hybrid research chatbot service.

Retrieval sources:

1. Indexed PDF chunks from:
   - research_documents
   - document_chunks

2. Publication metadata and abstracts from:
   - publications
   - publication_embeddings / lexical metadata

The chatbot prioritizes indexed PDF content and falls back to publication
metadata when useful.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast
from urllib.parse import urlparse
from uuid import UUID

from researchhub_ai.chat import SYSTEM_PROMPT, ChatProvider, ChatSource
from researchhub_ai.context import ContextManager, ContextPolicy, ContextSource
from researchhub_ai.embeddings import get_embedding_service
from sqlalchemy import Select, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from researchhub.core.config import get_settings
from researchhub.infrastructure.persistence.models import (
    ChatFeedback,
    ChatMessage,
    ChatSession,
    DocumentChunk,
    Journal,
    Publication,
    PublicationAuthor,
    Repository,
    ResearchDocument,
)

INJECTION_MARKERS = (
    "ignore previous instructions",
    "reveal the system prompt",
    "show api key",
    "database password",
    "run a shell command",
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedSource:
    """Normalized retrieval result used by the chat provider and citations."""

    source_id: UUID
    title: str
    text: str
    source_type: str

    publication_id: UUID | None = None
    document_id: UUID | None = None

    authors: tuple[str, ...] = ()
    publication_year: int | None = None

    url: str | None = None
    source_code: str | None = None
    university: str | None = None
    repository: str | None = None
    document_type: str | None = None
    document_url: str | None = None
    landing_url: str | None = None

    page_start: int | None = None
    page_end: int | None = None
    chunk_index: int | None = None
    chunk_id: UUID | None = None
    section: str | None = None

    similarity_score: float | None = None


def research_retrieval_statement(
    query: str,
    *,
    limit: int,
    university_id: UUID | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    publication_ids: list[UUID] | None = None,
) -> Select[tuple[Publication]]:
    """Build publication metadata retrieval.

    This remains available as a fallback for publications that do not yet
    have indexed PDF chunks.
    """

    tokens = [token for token in _search_tokens(query) if len(token) >= 3][:8]

    statement = (
        select(Publication)
        .options(selectinload(Publication.authors).selectinload(PublicationAuthor.author))
        .where(Publication.is_deleted.is_(False))
    )

    if tokens:
        clauses: list[ColumnElement[bool]] = []

        for token in tokens:
            pattern = f"%{token}%"

            clauses.extend(
                (
                    Publication.title.ilike(pattern),
                    Publication.abstract.ilike(pattern),
                )
            )

        statement = statement.where(or_(*clauses))

    if university_id is not None:
        repository_match = exists(
            select(Repository.id).where(
                Repository.id == Publication.repository_id,
                Repository.university_id == university_id,
            )
        )

        journal_match = exists(
            select(Journal.id).where(
                Journal.id == Publication.journal_id,
                Journal.university_id == university_id,
            )
        )

        statement = statement.where(
            or_(
                repository_match,
                journal_match,
            )
        )

    if year_from is not None:
        statement = statement.where(Publication.publication_year >= year_from)

    if year_to is not None:
        statement = statement.where(Publication.publication_year <= year_to)

    if publication_ids:
        statement = statement.where(Publication.id.in_(publication_ids))

    return statement.order_by(
        Publication.quality_score.desc().nullslast(),
        Publication.created_at.desc(),
    ).limit(limit)


class ResearchChatService:
    """Chat service using hybrid PDF-chunk and publication retrieval."""

    def __init__(
        self,
        session: AsyncSession,
        provider: ChatProvider,
        *,
        max_sources: int = 8,
        context_manager: ContextManager | None = None,
        expose_context_diagnostics: bool = True,
    ) -> None:
        self.session = session
        self.provider = provider
        self.max_sources = max_sources
        self.settings = get_settings()
        self.context_manager = context_manager or ContextManager(ContextPolicy(memory_guard=False))
        self.expose_context_diagnostics = expose_context_diagnostics

    async def create_session(
        self,
        *,
        university_id: UUID | None,
        title: str | None,
    ) -> ChatSession:
        """Create a new research chat session."""

        item = ChatSession(
            university_id=university_id,
            title=(title or "New research conversation").strip()[:255],
        )

        self.session.add(item)

        await self.session.commit()
        await self.session.refresh(item)

        return item

    async def list_sessions(self) -> list[ChatSession]:
        """Return non-deleted chat sessions."""

        rows = await self.session.scalars(
            select(ChatSession)
            .where(ChatSession.is_deleted.is_(False))
            .order_by(ChatSession.updated_at.desc())
        )

        return list(rows.all())

    async def get_session(
        self,
        session_id: UUID,
        *,
        with_messages: bool = False,
    ) -> ChatSession | None:
        """Return one chat session."""

        statement = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.is_deleted.is_(False),
        )

        if with_messages:
            statement = statement.options(selectinload(ChatSession.messages))

        return cast(ChatSession | None, await self.session.scalar(statement))

    async def delete_session(
        self,
        session_id: UUID,
    ) -> bool:
        """Soft-delete a chat session."""

        item = await self.get_session(session_id)

        if item is None:
            return False

        item.is_deleted = True

        await self.session.commit()

        return True

    async def update_session(
        self,
        session_id: UUID,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
    ) -> ChatSession:
        item = await self.get_session(session_id)
        if item is None:
            raise LookupError("Chat session not found")
        if title is not None:
            item.title = title.strip()[:255]
        if is_pinned is not None:
            item.is_pinned = is_pinned
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def ask(
        self,
        message: str,
        *,
        session_id: UUID | None = None,
        university_id: UUID | None = None,
        university_ids: list[UUID] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        publication_ids: list[UUID] | None = None,
        document_ids: list[UUID] | None = None,
        pinned_chunk_ids: list[UUID] | None = None,
        repository_sources: list[str] | None = None,
        document_types: list[str] | None = None,
        languages: list[str] | None = None,
        minimum_similarity: float = 0.35,
        top_documents: int = 5,
        top_chunks: int = 10,
        include_full_text: bool = True,
        include_metadata: bool = True,
        mode: str = "ask",
        answer_length: str = "balanced",
        response_language: str = "English",
    ) -> tuple[ChatSession, ChatMessage]:
        """Retrieve grounded context and generate a chat response."""

        # Measure the entire operation:
        # validation + retrieval + model completion + persistence.
        started = perf_counter()

        cleaned = " ".join(message.split())

        if not cleaned:
            raise ValueError("Message cannot be blank")

        if year_from is not None and year_to is not None and year_from > year_to:
            raise ValueError("year_from must be less than or equal to year_to")

        if _looks_like_injection(cleaned):
            raise ValueError("The request contains instructions that cannot be processed safely")

        chat = await self.get_session(session_id) if session_id else None

        if session_id and chat is None:
            raise LookupError("Chat session not found")

        if chat is None:
            chat = ChatSession(
                university_id=university_id,
                title=cleaned[:80],
            )

            self.session.add(chat)
            await self.session.flush()

        elif university_id is not None and chat.university_id not in (None, university_id):
            raise PermissionError("The requested university is outside this chat session scope")

        scope = chat.university_id or university_id

        user_message = ChatMessage(
            session_id=chat.id,
            role="user",
            content=cleaned,
        )

        self.session.add(user_message)

        retrieved_sources = await self._retrieve_sources(
            cleaned,
            university_id=scope,
            university_ids=university_ids,
            year_from=year_from,
            year_to=year_to,
            publication_ids=publication_ids,
            document_ids=document_ids,
            pinned_chunk_ids=pinned_chunk_ids,
            repository_sources=repository_sources,
            document_types=document_types,
            languages=languages,
            minimum_similarity=minimum_similarity,
            top_documents=top_documents,
            top_chunks=top_chunks,
            include_full_text=include_full_text,
            include_metadata=include_metadata,
        )

        candidate_provider_sources = [_to_chat_source(item) for item in retrieved_sources]

        provider_question = _mode_question(cleaned, mode, answer_length, response_language)
        prepared = self.context_manager.prepare(
            provider_question,
            cast(list[ContextSource], candidate_provider_sources),
            system_prompt=SYSTEM_PROMPT,
        )
        source_map = {
            id(provider_source): retrieved_source
            for provider_source, retrieved_source in zip(
                candidate_provider_sources, retrieved_sources, strict=True
            )
        }
        provider_source_map = {
            id(provider_source): provider_source for provider_source in candidate_provider_sources
        }
        provider_sources = [
            replace(provider_source_map[id(evidence.source)], text=evidence.text)
            for evidence in prepared.evidence
        ]
        selected_retrieved_sources = [
            source_map[id(evidence.source)] for evidence in prepared.evidence
        ]

        logger.info(
            "chat_context mode=%s num_ctx=%d num_predict=%d candidates=%d selected=%d "
            "evidence_budget=%d evidence_tokens=%d duplicates=%d overlaps=%d compressed=%d",
            prepared.profile.mode.value,
            prepared.profile.num_ctx,
            prepared.profile.num_predict,
            prepared.candidate_count,
            len(prepared.evidence),
            prepared.budget.available_evidence_tokens,
            prepared.budget.selected_evidence_tokens,
            prepared.duplicate_count,
            prepared.overlap_count,
            prepared.compression_count,
        )

        completion = await self.provider.complete(
            provider_question,
            provider_sources,
            prepared=prepared,
        )

        latency_ms = max(
            1,
            round((perf_counter() - started) * 1000),
        )

        citations = [
            _retrieved_citation(item, index)
            for index, item in enumerate(
                selected_retrieved_sources,
                start=1,
            )
        ]

        warnings: list[str] = []

        if not selected_retrieved_sources:
            warnings.append("No supporting publications or indexed PDF chunks were retrieved.")

        elif not any(item.source_type == "document_chunk" for item in selected_retrieved_sources):
            warnings.append(
                "The response used publication metadata because no "
                "matching indexed PDF chunks were found."
            )

        retrieved_ids = [str(item.source_id) for item in selected_retrieved_sources]
        context_diagnostics = (
            completion.diagnostics or {} if self.expose_context_diagnostics else {}
        )
        resource_mode_code = {"NORMAL": 0, "LOW_MEMORY": 1, "CRITICAL": 2}.get(
            str(context_diagnostics.get("resource_mode")), 0
        )

        assistant = ChatMessage(
            session_id=chat.id,
            role="assistant",
            content=completion.answer,
            citations=citations,
            retrieved_publication_ids=retrieved_ids,
            model_name=completion.model,
            latency_ms=latency_ms,
            usage={
                "prompt_tokens": completion.prompt_tokens,
                "completion_tokens": completion.completion_tokens,
                "total_tokens": (completion.prompt_tokens + completion.completion_tokens),
                "retrieved_sources": len(selected_retrieved_sources),
                "retrieved_pdf_chunks": sum(
                    item.source_type == "document_chunk" for item in selected_retrieved_sources
                ),
                "retrieved_publications": sum(
                    item.source_type == "publication" for item in selected_retrieved_sources
                ),
                "resource_mode_code": resource_mode_code,
                "configured_num_ctx": int(context_diagnostics.get("configured_num_ctx", 0)),
                "estimated_prompt_tokens": int(
                    context_diagnostics.get("estimated_prompt_tokens", 0)
                ),
                "reserved_output_tokens": int(context_diagnostics.get("reserved_output_tokens", 0)),
                "selected_context_chunks": int(context_diagnostics.get("selected_chunks", 0)),
                "dropped_context_chunks": int(context_diagnostics.get("dropped_chunks", 0)),
                "context_truncated": int(bool(context_diagnostics.get("context_truncated", False))),
            },
            warnings=warnings,
        )

        self.session.add(assistant)

        chat.updated_at = datetime.now(UTC)
        chat.last_model_name = completion.model

        await self.session.commit()
        await self.session.refresh(assistant)

        return chat, assistant

    async def _retrieve_sources(
        self,
        query: str,
        *,
        university_id: UUID | None,
        university_ids: list[UUID] | None,
        year_from: int | None,
        year_to: int | None,
        publication_ids: list[UUID] | None,
        document_ids: list[UUID] | None,
        pinned_chunk_ids: list[UUID] | None,
        repository_sources: list[str] | None,
        document_types: list[str] | None,
        languages: list[str] | None,
        minimum_similarity: float,
        top_documents: int,
        top_chunks: int,
        include_full_text: bool,
        include_metadata: bool,
    ) -> list[RetrievedSource]:
        """Retrieve full-text PDF evidence first, then metadata fallback."""

        document_sources = (
            await self._retrieve_document_chunks(
                query,
                university_id=university_id,
                university_ids=university_ids,
                year_from=year_from,
                year_to=year_to,
                publication_ids=publication_ids,
                document_ids=document_ids,
                pinned_chunk_ids=pinned_chunk_ids,
                repository_sources=repository_sources,
                document_types=document_types,
                languages=languages,
                minimum_similarity=minimum_similarity,
                top_documents=top_documents,
                top_chunks=top_chunks,
            )
            if include_full_text
            else []
        )

        # When the question clearly targets one named document, do not dilute
        # the context with unrelated metadata-only publications.
        source_limit = min(
            self.max_sources,
            max(top_chunks, self.settings.rag_retrieval_candidates),
        )
        if document_sources and _is_specific_document_query(query, document_sources[0].title):
            return document_sources[:source_limit]

        results: list[RetrievedSource] = list(document_sources)
        remaining = source_limit - len(results)

        if remaining > 0 and include_metadata:
            publication_sources = await self._retrieve_publications(
                query,
                limit=max(remaining * 2, remaining),
                university_id=university_id,
                year_from=year_from,
                year_to=year_to,
                publication_ids=publication_ids,
            )

            linked_publication_ids = {
                item.publication_id for item in document_sources if item.publication_id is not None
            }
            existing_titles = {item.title.casefold() for item in results}

            for item in publication_sources:
                if len(results) >= source_limit:
                    break
                if item.publication_id in linked_publication_ids:
                    continue
                if item.title.casefold() in existing_titles:
                    continue
                results.append(item)
                existing_titles.add(item.title.casefold())

        return results[:source_limit]

    async def _retrieve_document_chunks(
        self,
        query: str,
        *,
        university_id: UUID | None,
        university_ids: list[UUID] | None,
        year_from: int | None,
        year_to: int | None,
        publication_ids: list[UUID] | None,
        document_ids: list[UUID] | None,
        pinned_chunk_ids: list[UUID] | None,
        repository_sources: list[str] | None,
        document_types: list[str] | None,
        languages: list[str] | None,
        minimum_similarity: float,
        top_documents: int,
        top_chunks: int,
    ) -> list[RetrievedSource]:
        """Retrieve pgvector candidates and expand the strongest document."""

        encoder = get_embedding_service(
            self.settings.embedding_model,
            self.settings.embedding_device,
        )
        query_embedding = await asyncio.to_thread(encoder.encode_query, query)

        distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")
        statement = (
            select(DocumentChunk, ResearchDocument, distance)
            .join(ResearchDocument, ResearchDocument.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.embedding.is_not(None),
                ResearchDocument.extraction_status == "indexed",
            )
        )

        if publication_ids:
            statement = statement.where(ResearchDocument.publication_id.in_(publication_ids))

        if document_ids:
            statement = statement.where(ResearchDocument.id.in_(document_ids))

        if repository_sources:
            statement = statement.where(ResearchDocument.source.in_(repository_sources))

        if university_id is not None:
            publication_scope_match = exists(
                select(Publication.id).where(
                    Publication.id == ResearchDocument.publication_id,
                    Publication.is_deleted.is_(False),
                    or_(
                        exists(
                            select(Repository.id).where(
                                Repository.id == Publication.repository_id,
                                Repository.university_id == university_id,
                            )
                        ),
                        exists(
                            select(Journal.id).where(
                                Journal.id == Publication.journal_id,
                                Journal.university_id == university_id,
                            )
                        ),
                    ),
                )
            )
            statement = statement.where(publication_scope_match)

        if university_ids:
            statement = statement.where(
                exists(
                    select(Publication.id).where(
                        Publication.id == ResearchDocument.publication_id,
                        Publication.is_deleted.is_(False),
                        or_(
                            exists(
                                select(Repository.id).where(
                                    Repository.id == Publication.repository_id,
                                    Repository.university_id.in_(university_ids),
                                )
                            ),
                            exists(
                                select(Journal.id).where(
                                    Journal.id == Publication.journal_id,
                                    Journal.university_id.in_(university_ids),
                                )
                            ),
                        ),
                    )
                )
            )

        if document_types:
            statement = statement.where(
                exists(
                    select(Publication.id).where(
                        Publication.id == ResearchDocument.publication_id,
                        Publication.source_type.in_(document_types),
                    )
                )
            )

        if languages:
            statement = statement.where(
                exists(
                    select(Publication.id).where(
                        Publication.id == ResearchDocument.publication_id,
                        Publication.language.in_(languages),
                    )
                )
            )

        if year_from is not None:
            statement = statement.where(
                exists(
                    select(Publication.id).where(
                        Publication.id == ResearchDocument.publication_id,
                        Publication.publication_year >= year_from,
                    )
                )
            )

        if year_to is not None:
            statement = statement.where(
                exists(
                    select(Publication.id).where(
                        Publication.id == ResearchDocument.publication_id,
                        Publication.publication_year <= year_to,
                    )
                )
            )

        candidate_limit = max(self.settings.rag_retrieval_candidates, top_chunks * 10, 60)
        rows = (
            await self.session.execute(statement.order_by(distance.asc()).limit(candidate_limit))
        ).all()

        if not rows:
            return []

        query_terms = set(_search_tokens(query))
        first_chunk, first_document, first_distance = rows[0]
        primary_title = first_document.title or _title_from_path(first_document.local_path)
        document_specific = _is_specific_document_query(query, primary_title)
        primary_document_id = first_document.id

        results: list[RetrievedSource] = []
        chunks_per_document: defaultdict[UUID, int] = defaultdict(int)
        selected_documents: set[UUID] = set()
        selection_limit = min(
            self.max_sources,
            max(top_chunks, self.settings.rag_retrieval_candidates),
        )

        # Detailed questions about a named paper need several sections from the
        # same document. Broad questions still favor document diversity.
        primary_chunk_limit = min(selection_limit, 12) if document_specific else 3
        secondary_chunk_limit = 1 if document_specific else 2

        for chunk, document, raw_distance in rows:
            if len(results) >= selection_limit:
                break

            title = document.title or _title_from_path(document.local_path)
            max_for_document = (
                primary_chunk_limit if document.id == primary_document_id else secondary_chunk_limit
            )
            if chunks_per_document[document.id] >= max_for_document:
                continue

            similarity_score = max(0.0, min(1.0, 1.0 - float(raw_distance)))
            if similarity_score < minimum_similarity and chunk.id not in (pinned_chunk_ids or []):
                continue

            if document.id not in selected_documents and len(selected_documents) >= top_documents:
                continue

            title_terms = set(_search_tokens(title))
            content_terms = set(_search_tokens(chunk.content[:3000]))
            lexical_overlap = len(query_terms.intersection(title_terms | content_terms))

            # Reject weak, unrelated candidates. The strongest named document
            # is retained because vector search already ranked it first.
            if (
                document.id != primary_document_id
                and similarity_score < 0.68
                and lexical_overlap == 0
            ):
                continue

            # For a named-document question, exclude other documents unless
            # the primary document does not provide enough chunks.
            if (
                document_specific
                and document.id != primary_document_id
                and chunks_per_document[primary_document_id] >= 3
            ):
                continue

            results.append(
                RetrievedSource(
                    source_id=document.publication_id or document.id,
                    publication_id=document.publication_id,
                    document_id=document.id,
                    title=title,
                    text=chunk.content,
                    source_type="document_chunk",
                    url=_safe_public_url(document.document_url)
                    or _safe_public_url(document.landing_url),
                    source_code=document.source,
                    university=_metadata_text(document.metadata_json, "university"),
                    repository=_metadata_text(document.metadata_json, "repository")
                    or document.source.upper(),
                    document_type=_metadata_text(document.metadata_json, "document_type")
                    or _metadata_text(document.metadata_json, "type"),
                    document_url=_safe_public_url(document.document_url),
                    landing_url=_safe_public_url(document.landing_url),
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_index=chunk.chunk_index,
                    chunk_id=chunk.id,
                    similarity_score=similarity_score,
                )
            )
            chunks_per_document[document.id] += 1
            selected_documents.add(document.id)

        return results

    async def _retrieve_publications(
        self,
        query: str,
        *,
        limit: int,
        university_id: UUID | None,
        year_from: int | None,
        year_to: int | None,
        publication_ids: list[UUID] | None,
    ) -> list[RetrievedSource]:
        """Retrieve metadata/abstract publication fallback sources."""

        statement = research_retrieval_statement(
            query,
            limit=limit,
            university_id=university_id,
            year_from=year_from,
            year_to=year_to,
            publication_ids=publication_ids,
        )

        publications = list((await self.session.scalars(statement)).unique().all())

        return [_publication_to_retrieved_source(item) for item in publications]

    async def add_feedback(
        self,
        message_id: UUID,
        rating: str,
        comment: str | None,
    ) -> ChatFeedback:
        """Store user feedback for an assistant message."""

        message = await self.session.get(
            ChatMessage,
            message_id,
        )

        if message is None or message.role != "assistant":
            raise LookupError("Assistant message not found")

        feedback = ChatFeedback(
            message_id=message_id,
            rating=rating,
            comment=comment,
        )

        self.session.add(feedback)

        await self.session.commit()
        await self.session.refresh(feedback)

        return feedback

    async def document_preview_path(self, document_id: UUID) -> Path:
        document = await self.session.get(ResearchDocument, document_id)
        if document is None:
            raise LookupError("Research document not found")
        path = Path(document.local_path).resolve()
        if path.suffix.casefold() != ".pdf" or not path.is_file():
            raise LookupError("Document preview is unavailable")
        return path


def _search_tokens(
    query: str,
) -> list[str]:
    """Return normalized lexical search terms."""

    stopwords = {
        "what",
        "which",
        "show",
        "find",
        "about",
        "from",
        "with",
        "research",
        "studies",
        "papers",
        "paper",
        "study",
        "the",
        "and",
        "for",
        "does",
        "were",
        "was",
        "are",
        "is",
        "into",
        "that",
        "this",
    }

    result: list[str] = []

    for raw_token in query.split():
        normalized = raw_token.strip(".,?!:;()[]{}\"'").casefold()

        if normalized and normalized not in stopwords:
            result.append(normalized)

    return result


def _is_specific_document_query(query: str, title: str) -> bool:
    """Return True when the question clearly names the retrieved document."""

    query_terms = set(_search_tokens(query))
    title_terms = set(_search_tokens(title))
    if not title_terms:
        return False
    overlap = len(query_terms.intersection(title_terms))
    overlap_ratio = overlap / max(1, len(title_terms))
    lowered = query.casefold()
    intent = any(
        term in lowered
        for term in (
            "this paper",
            "this study",
            "the study",
            "explain",
            "summarize",
            "in detail",
            "identified",
            "findings",
            "methodology",
            "conclusion",
        )
    )
    return overlap >= 3 or (intent and overlap_ratio >= 0.25)


def _looks_like_injection(
    message: str,
) -> bool:
    """Reject obvious prompt-injection patterns."""

    lowered = message.casefold()

    return any(marker in lowered for marker in INJECTION_MARKERS)


def _publication_to_retrieved_source(
    publication: Publication,
) -> RetrievedSource:
    """Normalize a publication database model."""

    authors = tuple(link.author.full_name for link in publication.authors if link.author)

    return RetrievedSource(
        source_id=publication.id,
        publication_id=publication.id,
        document_id=None,
        title=publication.title,
        text=(publication.abstract or "No abstract is available."),
        source_type="publication",
        authors=authors,
        publication_year=(publication.publication_year),
        url=_safe_public_url(publication.article_url),
        source_code=publication.source,
        repository=publication.source.upper(),
        document_type=publication.source_type,
        landing_url=_safe_public_url(publication.article_url),
    )


def _to_chat_source(
    item: RetrievedSource,
) -> ChatSource:
    """Convert normalized retrieval data into provider input."""

    page_label = _page_label(
        item.page_start,
        item.page_end,
    )

    source_prefix_parts: list[str] = []

    if item.source_code:
        source_prefix_parts.append(f"Repository source: {item.source_code.upper()}")

    if page_label:
        source_prefix_parts.append(page_label)

    if item.similarity_score is not None:
        source_prefix_parts.append(f"Similarity: {item.similarity_score:.3f}")

    prefix = ""

    if source_prefix_parts:
        prefix = " | ".join(source_prefix_parts) + "\n"

    return ChatSource(
        publication_id=str(item.source_id),
        title=item.title,
        text=prefix + item.text,
        authors=item.authors,
        year=item.publication_year,
        document_id=str(item.document_id) if item.document_id else None,
        chunk_id=str(item.chunk_id) if item.chunk_id else None,
        page_start=item.page_start,
        page_end=item.page_end,
        section=item.section,
        chunk_index=item.chunk_index,
        similarity=item.similarity_score,
    )


def _retrieved_citation(
    item: RetrievedSource,
    index: int,
) -> dict[str, object]:
    """Build a frontend-compatible citation object."""

    return {
        "index": index,
        # Kept for compatibility with the existing frontend.
        # For standalone indexed PDFs this contains the document UUID.
        "publication_id": str(item.publication_id) if item.publication_id else None,
        "document_id": (str(item.document_id) if item.document_id else None),
        "chunk_id": str(item.chunk_id) if item.chunk_id else None,
        "source_type": item.source_type,
        "title": item.title,
        "authors": list(item.authors),
        "publication_year": item.publication_year,
        "url": _safe_public_url(item.url),
        "university": item.university,
        "repository": item.repository,
        "source": item.source_code,
        "page_start": item.page_start,
        "page_end": item.page_end,
        "chunk_index": item.chunk_index,
        "similarity_score": item.similarity_score,
        "excerpt": item.text[:1200].strip(),
        "document_url": _safe_public_url(item.document_url),
        "landing_url": _safe_public_url(item.landing_url),
        "preview_url": (
            f"/backend-api/ai/documents/{item.document_id}/view" if item.document_id else None
        ),
        "document_type": item.document_type,
    }


def _safe_public_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def grounding_status(citations: list[dict[str, object]]) -> str:
    chunks = [item for item in citations if item.get("source_type") == "document_chunk"]
    similarities: list[float] = []
    for item in chunks:
        score = item.get("similarity_score")
        if isinstance(score, int | float):
            similarities.append(float(score))
    if len(chunks) >= 3 and similarities and max(similarities) >= 0.65:
        return "strong"
    if citations:
        return "partial"
    return "insufficient"


def follow_up_questions(mode: str, grounding: str) -> list[str]:
    if grounding == "insufficient":
        return [
            "Broaden the search to all repositories.",
            "Try a related topic with fewer filters.",
        ]
    questions = {
        "compare": [
            "Which methodological differences best explain the findings?",
            "Compare the reported limitations across these studies.",
            "Which study provides the strongest evidence?",
        ],
        "literature_review": [
            "What research gaps remain unresolved?",
            "Which findings contradict one another?",
            "Summarize the dominant methodological patterns.",
        ],
        "methodology": [
            "What sampling limitations were reported?",
            "Compare the data collection instruments.",
            "How was the evidence analyzed?",
        ],
    }
    return questions.get(
        mode,
        [
            "What methodology did the strongest study use?",
            "What limitations were reported?",
            "Show the evidence supporting this conclusion.",
        ],
    )


def _metadata_text(metadata: dict[object, object] | None, key: str) -> str | None:
    value = (metadata or {}).get(key)
    return str(value).strip() if isinstance(value, str) and value.strip() else None


def _mode_question(message: str, mode: str, answer_length: str, language: str) -> str:
    instructions = {
        "summarize": "Summarize the retrieved research with findings, methods, and limitations.",
        "compare": "Compare the studies by objective, methodology, sample, findings, and limitations.",
        "methodology": "Extract the design, sample, instruments, analysis, and methodological limitations.",
        "evidence": "Prioritize page-level evidence supporting each conclusion.",
        "literature_review": "Synthesize themes, agreement, contradictions, methods, gaps, and future research.",
        "citation": "Generate a complete citation from only the available metadata.",
        "explain": "Explain the findings clearly in plain language while preserving citations.",
        "ask": "Answer the research question directly.",
    }
    return (
        f"{message}\n\nTask: {instructions.get(mode, instructions['ask'])} "
        f"Use a {answer_length} response in {language}."
    )


def _title_from_path(
    path: str,
) -> str:
    """Create a readable title from a stored file path."""

    filename = path.replace("\\", "/").rsplit(
        "/",
        maxsplit=1,
    )[-1]

    if filename.casefold().endswith(".pdf"):
        filename = filename[:-4]

    # Downloaded files often begin with UUIDs or numeric IDs.
    if "_" in filename:
        prefix, remainder = filename.split(
            "_",
            maxsplit=1,
        )

        if _looks_like_identifier(prefix):
            filename = remainder

    return filename.strip() or "Indexed research document"


def _looks_like_identifier(
    value: str,
) -> bool:
    """Return whether a filename prefix resembles an ID."""

    compact = value.replace("-", "")

    return compact.isdigit() or (
        len(compact) == 32 and all(character in "0123456789abcdefABCDEF" for character in compact)
    )


def _page_label(
    page_start: int | None,
    page_end: int | None,
) -> str | None:
    """Create a readable page range label."""

    if page_start is None:
        return None

    if page_end is None or page_end == page_start:
        return f"Page {page_start}"

    return f"Pages {page_start}-{page_end}"
