"""Centralized, idempotent publication embedding generation."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from researchhub_ai.embeddings import Encoder
from researchhub_ai.text_builder import PublicationTextBuilder
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from researchhub.infrastructure.persistence.models import (
    Publication,
    PublicationAuthor,
    PublicationEmbeddingRecord,
    PublicationKeyword,
)

LOGGER = logging.getLogger(__name__)
EXPECTED_DIMENSION = 384


def candidate_statement(
    *, source: str, force: bool, after_id: UUID | None = None, limit: int | None = None
) -> Select[tuple[Publication]]:
    """Backward-compatible stable keyset query used by batch jobs and tests."""

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


@dataclass(slots=True)
class EmbeddingRunResult:
    scanned: int
    eligible: int
    generated: int
    skipped: int
    stale: int
    failed: int
    elapsed_seconds: float
    model: str
    dimension: int
    device: str

    @property
    def candidates(self) -> int:
        return self.eligible

    @property
    def processed(self) -> int:
        return self.generated

    @property
    def duration(self) -> float:
        return self.elapsed_seconds

    @property
    def records_per_second(self) -> float:
        return self.generated / self.elapsed_seconds if self.elapsed_seconds else 0.0

    def asdict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "candidates": self.candidates,
            "processed": self.processed,
            "duration": self.duration,
            "records_per_second": self.records_per_second,
        }


class PublicationEmbeddingProcessor:
    """Generate compatibility vectors and canonical versioned records together."""

    def __init__(self, session: AsyncSession, encoder: Encoder, *, device: str = "cpu") -> None:
        self.session = session
        self.encoder = encoder
        self.device = device
        self.text_builder = PublicationTextBuilder()

    def _dimension(self) -> int:
        dimension = self.encoder.get_embedding_dimension()
        if dimension != EXPECTED_DIMENSION:
            raise ValueError(
                f"Expected {EXPECTED_DIMENSION}-dimensional embeddings, received {dimension}"
            )
        return dimension

    @staticmethod
    def _options() -> tuple[Any, ...]:
        return (
            selectinload(Publication.authors).selectinload(PublicationAuthor.author),
            selectinload(Publication.keywords).selectinload(PublicationKeyword.keyword),
            selectinload(Publication.journal),
            selectinload(Publication.publication_type),
        )

    async def embed_publication(self, publication_id: UUID, *, force: bool = False) -> bool:
        dimension = self._dimension()
        publication = await self.session.scalar(
            select(Publication).options(*self._options()).where(Publication.id == publication_id)
        )
        if publication is None or publication.is_deleted:
            raise LookupError("Publication not found")
        built = self.text_builder.build_embedding_text(publication)
        model = self.encoder.get_model_name()
        if (
            not force
            and publication.embedding is not None
            and publication.embedding_model == model
            and publication.embedding_content_hash == built.content_hash
        ):
            return False
        try:
            vectors = self.encoder.encode_documents([built.text], batch_size=1)
            if len(vectors) != 1 or len(vectors[0]) != dimension:
                raise ValueError("Embedding model returned an invalid vector dimension")
            vector = list(vectors[0])
            now = datetime.now(UTC)
            publication.embedding = vector
            publication.embedding_model = model
            publication.embedded_at = now
            publication.embedding_content_hash = built.content_hash
            publication.embedding_failure_code = None
            publication.embedding_failure_message = None
            publication.embedding_retry_count = 0
            statement = insert(PublicationEmbeddingRecord).values(
                publication_id=publication.id,
                model_name=model,
                model_version=None,
                embedding_dimension=dimension,
                embedding=vector,
                input_text=built.text,
                content_hash=built.content_hash,
            )
            statement = statement.on_conflict_do_update(
                index_elements=["publication_id", "model_name"],
                set_={
                    "embedding_dimension": dimension,
                    "embedding": vector,
                    "input_text": built.text,
                    "content_hash": built.content_hash,
                    "updated_at": now,
                },
            )
            await self.session.execute(statement)
            await self.session.commit()
            return True
        except Exception as exc:
            await self.session.rollback()
            publication = await self.session.get(Publication, publication_id)
            if publication is not None:
                publication.embedding_failure_code = type(exc).__name__[:80]
                publication.embedding_failure_message = str(exc)[:2000]
                publication.embedding_retry_count += 1
                await self.session.commit()
            raise

    async def run(
        self,
        *,
        source: str | None = None,
        university_id: UUID | None = None,
        batch_size: int = 32,
        database_batch_size: int = 300,
        limit: int | None = None,
        force: bool = False,
        failed_only: bool = False,
        dry_run: bool = False,
    ) -> EmbeddingRunResult:
        if batch_size < 1 or database_batch_size < 1:
            raise ValueError("Batch sizes must be greater than zero")
        dimension = self._dimension()
        started = time.monotonic()
        base = select(Publication).where(
            Publication.is_deleted.is_(False), Publication.title.is_not(None)
        )
        if source:
            base = base.where(Publication.source == source)
        if university_id:
            from researchhub.infrastructure.persistence.models import Repository

            base = base.join(Repository).where(Repository.university_id == university_id)
        if failed_only:
            base = base.where(Publication.embedding_failure_code.is_not(None))
        elif not force:
            base = base.where(
                or_(
                    Publication.embedding.is_(None),
                    Publication.embedding_model != self.encoder.get_model_name(),
                    Publication.embedding_content_hash.is_(None),
                )
            )
        scanned = int(
            await self.session.scalar(
                select(func.count(Publication.id)).where(Publication.is_deleted.is_(False))
            )
            or 0
        )
        eligible = int(
            await self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        )
        target = min(eligible, limit) if limit else eligible
        stale = generated = failed = skipped = 0
        if dry_run:
            return EmbeddingRunResult(
                scanned=scanned,
                eligible=target,
                generated=0,
                skipped=target,
                stale=0,
                failed=0,
                elapsed_seconds=time.monotonic() - started,
                model=self.encoder.get_model_name(),
                dimension=dimension,
                device=self.device,
            )

        after_id: UUID | None = None
        while generated + skipped < target:
            page_size = min(database_batch_size, target - generated - skipped)
            statement = base.options(*self._options()).order_by(Publication.id)
            if after_id:
                statement = statement.where(Publication.id > after_id)
            publications = list((await self.session.scalars(statement.limit(page_size))).all())
            if not publications:
                break
            try:
                built_texts = [
                    self.text_builder.build_embedding_text(item) for item in publications
                ]
                vectors = self.encoder.encode_documents(
                    [item.text for item in built_texts], batch_size=batch_size
                )
                if len(vectors) != len(publications):
                    raise RuntimeError("Embedding model returned an unexpected number of vectors")
                now = datetime.now(UTC)
                for publication, built, vector in zip(
                    publications, built_texts, vectors, strict=True
                ):
                    if len(vector) != dimension:
                        raise ValueError("Embedding model returned an invalid vector dimension")
                    if publication.embedding is not None:
                        stale += 1
                    publication.embedding = list(vector)
                    publication.embedding_model = self.encoder.get_model_name()
                    publication.embedded_at = now
                    publication.embedding_content_hash = built.content_hash
                    publication.embedding_failure_code = None
                    publication.embedding_failure_message = None
                    publication.embedding_retry_count = 0
                    if hasattr(self.session, "execute"):
                        version = insert(PublicationEmbeddingRecord).values(
                            publication_id=publication.id,
                            model_name=self.encoder.get_model_name(),
                            embedding_dimension=dimension,
                            embedding=list(vector),
                            input_text=built.text,
                            content_hash=built.content_hash,
                        )
                        await self.session.execute(
                            version.on_conflict_do_update(
                                index_elements=["publication_id", "model_name"],
                                set_={
                                    "embedding_dimension": dimension,
                                    "embedding": list(vector),
                                    "input_text": built.text,
                                    "content_hash": built.content_hash,
                                    "updated_at": now,
                                },
                            )
                        )
                await self.session.commit()
            except Exception:
                await self.session.rollback()
                raise
            generated += len(publications)
            after_id = publications[-1].id
        return EmbeddingRunResult(
            scanned=scanned,
            eligible=target,
            generated=generated,
            skipped=skipped,
            stale=stale,
            failed=failed,
            elapsed_seconds=time.monotonic() - started,
            model=self.encoder.get_model_name(),
            dimension=dimension,
            device=self.device,
        )
