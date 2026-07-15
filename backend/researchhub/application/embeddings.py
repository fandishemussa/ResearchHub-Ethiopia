"""Bounded, resumable publication embedding generation."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from researchhub_ai.embeddings import Encoder, build_publication_text
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from researchhub.infrastructure.persistence.models import Publication

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class EmbeddingRunResult:
    """Serializable embedding run metrics."""

    candidates: int
    processed: int
    elapsed_seconds: float
    model: str
    dimension: int
    device: str

    @property
    def records_per_second(self) -> float:
        return self.processed / self.elapsed_seconds if self.elapsed_seconds else 0.0

    def asdict(self) -> dict[str, object]:
        return {**asdict(self), "records_per_second": self.records_per_second}


def candidate_statement(
    *, source: str, force: bool, after_id: UUID | None = None, limit: int | None = None
) -> Select[tuple[Publication]]:
    """Build the stable UUID keyset candidate query."""

    statement = select(Publication).where(
        Publication.source == source,
        Publication.is_deleted.is_(False),
        Publication.title.is_not(None),
    )
    if not force:
        statement = statement.where(Publication.embedding.is_(None))
    if after_id is not None:
        statement = statement.where(Publication.id > after_id)
    statement = statement.order_by(Publication.id)
    return statement.limit(limit) if limit is not None else statement


class PublicationEmbeddingProcessor:
    """Generate and persist embeddings one committed database page at a time."""

    def __init__(self, session: AsyncSession, encoder: Encoder, *, device: str = "cpu") -> None:
        self.session = session
        self.encoder = encoder
        self.device = device

    async def count_candidates(self, source: str, force: bool) -> int:
        statement = select(func.count(Publication.id)).where(
            Publication.source == source,
            Publication.is_deleted.is_(False),
            Publication.title.is_not(None),
        )
        if not force:
            statement = statement.where(Publication.embedding.is_(None))
        return int(await self.session.scalar(statement) or 0)

    async def run(
        self,
        *,
        source: str,
        batch_size: int = 32,
        database_batch_size: int = 300,
        limit: int | None = None,
        force: bool = False,
    ) -> EmbeddingRunResult:
        if batch_size < 1 or database_batch_size < 1:
            raise ValueError("Batch sizes must be greater than zero")
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than zero")
        dimension = self.encoder.get_embedding_dimension()
        if dimension != 384:
            raise ValueError(f"Expected 384-dimensional embeddings, received {dimension}")

        candidates = await self.count_candidates(source, force)
        target = min(candidates, limit) if limit is not None else candidates
        started = time.monotonic()
        processed = 0
        after_id: UUID | None = None
        LOGGER.info(
            "Embedding run: candidates=%d target=%d model=%s device=%s dimension=%d",
            candidates,
            target,
            self.encoder.get_model_name(),
            self.device,
            dimension,
        )

        while processed < target:
            page_size = min(database_batch_size, target - processed)
            publications = list(
                (
                    await self.session.scalars(
                        candidate_statement(
                            source=source,
                            force=force,
                            after_id=after_id,
                            limit=page_size,
                        )
                    )
                ).all()
            )
            if not publications:
                break
            try:
                texts = [
                    build_publication_text(item.title, item.abstract, item.subjects)
                    for item in publications
                ]
                vectors = self.encoder.encode_documents(texts, batch_size=batch_size)
                if len(vectors) != len(publications):
                    raise RuntimeError("Embedding model returned an unexpected number of vectors")
                now = datetime.now(UTC)
                for publication, vector in zip(publications, vectors, strict=True):
                    if len(vector) != dimension:
                        raise ValueError("Embedding vector has an invalid dimension")
                    publication.embedding = vector
                    publication.embedding_model = self.encoder.get_model_name()
                    publication.embedded_at = now
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                raise
            after_id = publications[-1].id
            processed += len(publications)
            elapsed = time.monotonic() - started
            LOGGER.info(
                "Embedded %d/%d publications (%.2f records/s)",
                processed,
                target,
                processed / elapsed if elapsed else 0.0,
            )

        return EmbeddingRunResult(
            candidates=candidates,
            processed=processed,
            elapsed_seconds=time.monotonic() - started,
            model=self.encoder.get_model_name(),
            dimension=dimension,
            device=self.device,
        )
