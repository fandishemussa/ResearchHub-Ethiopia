"""Indexed research-document queries and secure content resolution."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.infrastructure.persistence.models import DocumentChunk, ResearchDocument


class ResearchDocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_documents(
        self,
        *,
        limit: int,
        offset: int,
        source: str | None,
        status: str | None,
        search: str | None,
    ) -> tuple[list[dict[str, object]], int]:
        criteria = []
        if source:
            criteria.append(ResearchDocument.source == source)
        if status:
            criteria.append(ResearchDocument.extraction_status == status)
        if search:
            criteria.append(ResearchDocument.title.ilike(f"%{search.strip()}%"))
        total = int(
            await self.session.scalar(select(func.count(ResearchDocument.id)).where(*criteria)) or 0
        )
        rows = await self.session.execute(
            self._detail_statement()
            .where(*criteria)
            .order_by(ResearchDocument.extracted_at.desc().nullslast(), ResearchDocument.title)
            .limit(limit)
            .offset(offset)
        )
        return [self._row(item) for item in rows], total

    async def get(self, document_id: UUID) -> dict[str, object] | None:
        row = (
            await self.session.execute(
                self._detail_statement().where(ResearchDocument.id == document_id)
            )
        ).first()
        return self._row(row) if row else None

    async def chunks(
        self,
        document_id: UUID,
        *,
        limit: int,
        offset: int,
        search: str | None,
        page: int | None,
        section: str | None,
        content_type: str | None,
    ) -> tuple[list[dict[str, object]], int]:
        if await self.session.get(ResearchDocument, document_id) is None:
            raise LookupError("Research document not found")
        criteria = [DocumentChunk.document_id == document_id]
        if search:
            criteria.append(DocumentChunk.content.ilike(f"%{search.strip()}%"))
        if page is not None:
            criteria.extend(
                [
                    DocumentChunk.page_start <= page,
                    func.coalesce(DocumentChunk.page_end, DocumentChunk.page_start) >= page,
                ]
            )
        if section:
            criteria.append(DocumentChunk.section_title.ilike(f"%{section.strip()}%"))
        if content_type:
            criteria.append(
                DocumentChunk.chunk_metadata["content_type"].astext.ilike(
                    f"%{content_type.strip()}%"
                )
            )
        total = int(
            await self.session.scalar(select(func.count(DocumentChunk.id)).where(*criteria)) or 0
        )
        items = list(
            (
                await self.session.scalars(
                    select(DocumentChunk)
                    .where(*criteria)
                    .order_by(DocumentChunk.page_start.nullslast(), DocumentChunk.chunk_index)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )
        return [self._chunk(item) for item in items], total

    async def content_path(self, document_id: UUID) -> Path:
        item = await self.session.get(ResearchDocument, document_id)
        if item is None:
            raise LookupError("Research document not found")
        path = Path(item.local_path).resolve()
        if path.suffix.casefold() != ".pdf" or not path.is_file():
            raise LookupError("Document preview is unavailable")
        return path

    @staticmethod
    def _detail_statement():
        return (
            select(
                ResearchDocument,
                func.count(DocumentChunk.id).label("chunk_count"),
                func.coalesce(func.sum(DocumentChunk.character_count), 0).label("character_count"),
                func.count(DocumentChunk.embedding).label("embedded_chunk_count"),
                func.max(DocumentChunk.embedding_model).label("embedding_model"),
            )
            .outerjoin(DocumentChunk, DocumentChunk.document_id == ResearchDocument.id)
            .group_by(ResearchDocument.id)
        )

    @staticmethod
    def _row(row) -> dict[str, object]:
        document, chunk_count, character_count, embedded_chunk_count, embedding_model = row
        return {
            "id": document.id,
            "publication_id": document.publication_id,
            "source": document.source,
            "title": document.title,
            "document_url": _public_url(document.document_url),
            "landing_url": _public_url(document.landing_url),
            "mime_type": document.mime_type,
            "file_size_bytes": document.file_size_bytes,
            "page_count": document.page_count,
            "extraction_status": document.extraction_status,
            "extraction_error": document.extraction_error,
            "metadata": document.metadata_json,
            "extracted_at": document.extracted_at,
            "chunk_count": int(chunk_count),
            "character_count": int(character_count),
            "embedded_chunk_count": int(embedded_chunk_count),
            "embedding_model": embedding_model,
        }

    @staticmethod
    def _chunk(item: DocumentChunk) -> dict[str, object]:
        metadata = item.chunk_metadata or {}
        return {
            "id": item.id,
            "document_id": item.document_id,
            "chunk_index": item.chunk_index,
            "page_start": item.page_start,
            "page_end": item.page_end,
            "section_title": item.section_title,
            "content": item.content,
            "character_count": item.character_count,
            "embedding_model": item.embedding_model,
            "embedded_at": item.embedded_at,
            "content_type": metadata.get("content_type"),
        }


def _public_url(value: str | None) -> str | None:
    return value if value and value.startswith(("https://", "http://")) else None
