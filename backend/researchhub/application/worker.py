"""Celery worker entrypoint for asynchronous harvesting and enrichment tasks."""

import asyncio
import hashlib
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from celery import Celery, Task
from researchhub_ai.embeddings import get_embedding_service
from researchhub_harvester.config import (
    HarvestConnectorDefinition,
    HarvestEngineConfig,
    load_harvest_config,
)
from researchhub_harvester.services.engine import (
    HarvestEngine,
    aggregate_reports,
)
from sqlalchemy import select

from researchhub.application.document_indexer import index_pdf
from researchhub.application.embeddings import PublicationEmbeddingProcessor
from researchhub.application.harvest_store import SQLAlchemyHarvestStore
from researchhub.application.publication_documents import DocumentSourceProbe
from researchhub.core.config import get_settings
from researchhub.infrastructure.persistence.models import (
    Connector,
    HarvestJob,
    Publication,
    ResearchDocument,
)
from researchhub.infrastructure.persistence.session import SessionLocal, engine

# ---------------------------------------------------------------------------
# Settings and Celery application
# These must be defined before any @celery_app.task decorator.
# ---------------------------------------------------------------------------

settings = get_settings()

celery_app = Celery(
    "researchhub",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,
    task_acks_late=True,
    task_acks_on_failure_or_timeout=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)

celery_app.conf.task_routes = {
    "researchhub.harvest.*": {"queue": "harvest"},
    "researchhub.imports.*": {"queue": "imports"},
    "researchhub.embeddings.*": {"queue": "ai_embeddings"},
    "researchhub.ai.generate.*": {"queue": "ai_generation"},
    "researchhub.ai.analyze.*": {"queue": "ai_analysis"},
    "researchhub.ai.chat.*": {"queue": "ai_chat"},
    "researchhub.documents.*": {"queue": "documents"},
    "researchhub.notifications.*": {"queue": "notifications"},
    "researchhub.maintenance.*": {"queue": "maintenance"},
}
celery_app.conf.beat_schedule = {
    "bounded-missing-publication-embeddings": {
        "task": "researchhub.embeddings.generate",
        "schedule": 3600.0,
        "kwargs": {"limit": 500},
    }
}


# ---------------------------------------------------------------------------
# Document indexing
# ---------------------------------------------------------------------------


# Celery does not publish typing for its task decorator; the function remains fully annotated.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="researchhub.documents.download_publication",
    queue="documents",
    bind=True,
    autoretry_for=(httpx.TimeoutException, httpx.NetworkError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def download_publication_document(
    self: Task, document_id: str, publication_id: str
) -> dict[str, Any]:
    """Download one pre-probed PDF and continue through the canonical indexer."""

    return _run_task(_download_publication_document(document_id, publication_id))


async def _download_publication_document(document_id: str, publication_id: str) -> dict[str, Any]:
    document_uuid = UUID(document_id)
    publication_uuid = UUID(publication_id)
    async with SessionLocal() as session:
        document = await session.get(ResearchDocument, document_uuid)
        publication = await session.get(Publication, publication_uuid)
        if document is None or publication is None or not document.document_url:
            raise LookupError("Document registration or publication is missing")
        path = Path(document.local_path)
        part_path = path.with_suffix(path.suffix + ".part")
        document.extraction_status = "downloading"
        document.last_attempted_at = datetime.now(UTC)
        await session.commit()
        maximum = settings.document_download_max_size_mb * 1024 * 1024
        digest = hashlib.sha256()
        size = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        timeout = httpx.Timeout(
            connect=settings.http_connect_timeout_seconds,
            read=settings.http_read_timeout_seconds,
            write=settings.http_read_timeout_seconds,
            pool=settings.http_connect_timeout_seconds,
        )
        try:
            source_status = await DocumentSourceProbe(settings).probe(document.document_url)
            if (
                not source_status.reachable
                or not source_status.is_pdf
                or not source_status.final_url
            ):
                raise ValueError(source_status.error_code or "document_source_unavailable")
            document.document_url = source_status.final_url
            async with (
                httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    max_redirects=settings.document_probe_redirect_limit,
                    headers={
                        "User-Agent": "ResearchHub-Ethiopia/1.0",
                        "Accept-Encoding": "identity",
                    },
                ) as client,
                client.stream("GET", document.document_url) as response,
            ):
                response.raise_for_status()
                with part_path.open("wb") as output:
                    async for block in response.aiter_bytes(1024 * 1024):
                        size += len(block)
                        if size > maximum:
                            raise ValueError("document_too_large")
                        digest.update(block)
                        output.write(block)
            with part_path.open("rb") as input_file:
                if input_file.read(5) != b"%PDF-":
                    raise ValueError("invalid_pdf_signature")
            part_path.replace(path)
            document.checksum_sha256 = digest.hexdigest()
            document.file_size_bytes = size
            document.downloaded_at = datetime.now(UTC)
            document.extraction_status = "downloaded"
            duplicate = await session.scalar(
                select(ResearchDocument).where(
                    ResearchDocument.checksum_sha256 == document.checksum_sha256,
                    ResearchDocument.id != document.id,
                )
            )
            if duplicate:
                document.metadata_json = {
                    **document.metadata_json,
                    "duplicate_of": str(duplicate.id),
                }
            await session.commit()
            return await index_pdf(
                session,
                path=path,
                source=document.source,
                publication_id=publication.id,
                title=publication.title,
                external_id=publication.external_id,
                document_url=document.document_url,
                landing_url=document.landing_url,
                metadata=document.metadata_json,
            )
        except Exception as exc:
            if part_path.exists():
                part_path.unlink()
            await session.rollback()
            document = await session.get(ResearchDocument, document_uuid)
            if document:
                document.extraction_status = "failed"
                document.extraction_error = "The document could not be downloaded or validated."
                document.processing_error_code = type(exc).__name__[:80]
                document.technical_error = repr(exc)[:5000]
                document.retry_count += 1
                await session.commit()
            raise


# Celery does not publish typing for its task decorator; the function remains fully annotated.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="researchhub.documents.index_file",
    queue="documents",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def index_document_file(
    self: Task,
    file_path: str,
    source: str,
    publication_id: str | None = None,
    title: str | None = None,
    external_id: str | None = None,
    document_url: str | None = None,
    landing_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract, chunk, embed, and persist one PDF document."""

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Document does not exist: {path}")

    return _run_task(
        _index_document_file(
            path=path,
            source=source,
            publication_id=publication_id,
            title=title,
            external_id=external_id,
            document_url=document_url,
            landing_url=landing_url,
            metadata=metadata,
        )
    )


async def _index_document_file(
    *,
    path: Path,
    source: str,
    publication_id: str | None,
    title: str | None,
    external_id: str | None,
    document_url: str | None,
    landing_url: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Run the database-aware PDF indexing pipeline."""

    async with SessionLocal() as session:
        return await index_pdf(
            session,
            path=path,
            source=source,
            publication_id=UUID(publication_id) if publication_id else None,
            title=title or path.stem,
            external_id=external_id,
            document_url=document_url,
            landing_url=landing_url,
            metadata=metadata
            or {
                "source": source,
                "filename": path.name,
            },
        )


# ---------------------------------------------------------------------------
# Worker health
# ---------------------------------------------------------------------------


# Celery does not publish typing for its task decorator; the function remains fully annotated.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="researchhub.healthcheck"
)
def healthcheck() -> str:
    """Return a simple worker health signal."""

    return "ok"


# ---------------------------------------------------------------------------
# Harvest tasks
# ---------------------------------------------------------------------------


# Celery does not publish typing for its task decorator; the function remains fully annotated.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="researchhub.harvest.run_config"
)
def run_harvest_config(
    config_path: str | None = None,
) -> dict[str, object]:
    """Run all enabled connectors from a JSON config path."""

    path = config_path or settings.harvest_config_path

    if not path:
        raise ValueError("No harvest config path configured")

    return _run_task(_run_all(path))


# Celery does not publish typing for its task decorator; the function remains fully annotated.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="researchhub.harvest.run_connector"
)
def run_harvest_connector(
    connector_code: str,
    config_path: str | None = None,
) -> dict[str, object]:
    """Run one connector from a JSON config path."""

    path = config_path or settings.harvest_config_path

    if not path:
        raise ValueError("No harvest config path configured")

    return _run_task(_run_one(path, connector_code))


async def _run_all(config_path: str) -> dict[str, object]:
    """Execute every enabled connector."""

    harvest_engine = HarvestEngine(
        load_harvest_config(config_path),
        store=SQLAlchemyHarvestStore(),
    )

    reports = await harvest_engine.run_all()

    return aggregate_reports(reports)


async def _run_one(
    config_path: str,
    connector_code: str,
) -> dict[str, object]:
    """Execute one connector by code."""

    harvest_engine = HarvestEngine(
        load_harvest_config(config_path),
        store=SQLAlchemyHarvestStore(),
    )

    report = await harvest_engine.run_connector(connector_code)

    return report.asdict()


# Celery does not publish typing for its task decorator; the function remains fully annotated.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="researchhub.harvest.run_source"
)
def run_source_harvest(job_id: str) -> dict[str, object]:
    """Execute one database-configured source harvest."""

    return _run_task(_run_source_harvest(job_id))


async def _run_source_harvest(job_id: str) -> dict[str, object]:
    """Load a stored harvest job and execute its connector."""

    from uuid import UUID

    job_uuid = UUID(job_id)

    async with SessionLocal() as session:
        job = await session.get(HarvestJob, job_uuid)

        if job is None:
            raise LookupError("Harvest job not found")

        source = await session.get(Connector, job.connector_id)

        if source is None:
            raise LookupError("Source not found")

        source_type = source.connector_type.replace("-", "_")
        connector_type = (
            "oai-pmh"
            if source_type in {"oai_pmh", "dspace_oai", "ojs_oai"}
            else source_type.replace("_", "-")
        )
        definition = HarvestConnectorDefinition(
            code=source.code,
            name=source.name,
            connector_type=connector_type,
            base_url=source.oai_endpoint or source.api_url or source.base_url or "",
            source_type=source_type,
            metadata_prefix=str(job.metadata_json.get("metadata_prefix") or source.metadata_prefix),
            set_spec=job.metadata_json.get("set_spec") or source.set_spec,
            from_date=job.since,
            until_date=job.until,
            connector_id=source.id,
            university_id=source.university_id,
            repository_id=source.repository_id,
            timeout_seconds=settings.harvest_request_timeout_seconds,
            max_retries=settings.harvest_max_retries,
            extra={
                **(source.config or {}),
                "maximum_records": job.metadata_json.get("maximum_records"),
                "include_deleted_records": job.metadata_json.get("include_deleted_records", True),
            },
        )

        dry_run = job.dry_run
        source_code = source.code

    store = SQLAlchemyHarvestStore(
        existing_job_id=job_uuid,
        dry_run=dry_run,
    )

    harvest_engine = HarvestEngine(
        HarvestEngineConfig(
            connectors=[definition],
            job_max_attempts=1,
        ),
        store=store,
    )

    report = await harvest_engine.run_connector(source_code)

    if not dry_run:
        celery_app.send_task(
            "researchhub.embeddings.generate",
            kwargs={"source": source_code},
            task_id=f"source-embeddings-{source_code}-{job_id}",
        )

    return report.asdict()


# ---------------------------------------------------------------------------
# Embedding tasks
# ---------------------------------------------------------------------------


# Celery does not publish typing for its task decorator; the function remains fully annotated.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="researchhub.embeddings.generate"
)
def generate_embeddings(
    source: str | None = None,
    university_id: str | None = None,
    model: str | None = None,
    limit: int | None = None,
    force: bool = False,
    batch_size: int = 32,
    database_batch_size: int = 300,
    failed_only: bool = False,
) -> dict[str, object]:
    """Generate resumable publication embeddings."""

    return _run_task(
        _generate_embeddings(
            source=source,
            university_id=university_id,
            model=model or settings.embedding_model,
            limit=limit,
            force=force,
            batch_size=batch_size,
            database_batch_size=database_batch_size,
            failed_only=failed_only,
        )
    )


# Celery does not publish typing for its task decorator; the function remains fully annotated.
@celery_app.task(  # type: ignore[untyped-decorator]
    name="researchhub.embeddings.generate_publication",
    queue="ai_embeddings",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def generate_publication_embedding(publication_id: str, force: bool = False) -> dict[str, object]:
    """Idempotently generate one publication embedding."""

    return _run_task(_generate_publication_embedding(publication_id, force=force))


async def _generate_publication_embedding(publication_id: str, *, force: bool) -> dict[str, object]:
    from uuid import UUID

    encoder = get_embedding_service(settings.embedding_model, settings.embedding_device)
    async with SessionLocal() as session:
        processor = PublicationEmbeddingProcessor(
            session, encoder, device=settings.embedding_device
        )
        generated = await processor.embed_publication(UUID(publication_id), force=force)
        return {
            "publication_id": publication_id,
            "generated": generated,
            "model": encoder.get_model_name(),
            "dimension": encoder.get_embedding_dimension(),
        }


def _run_task[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run a Celery coroutine and release loop-bound connections."""

    async def execute() -> T:
        try:
            return await coroutine
        finally:
            await engine.dispose()

    return asyncio.run(execute())


async def _generate_embeddings(
    *,
    source: str | None,
    university_id: str | None,
    model: str,
    limit: int | None,
    force: bool,
    batch_size: int,
    database_batch_size: int,
    failed_only: bool,
) -> dict[str, object]:
    """Generate embeddings for stored publications."""

    encoder = get_embedding_service(
        model,
        settings.embedding_device,
    )

    async with SessionLocal() as session:
        processor = PublicationEmbeddingProcessor(
            session,
            encoder,
            device=settings.embedding_device,
        )

        result = await processor.run(
            source=source,
            university_id=UUID(university_id) if university_id else None,
            limit=limit,
            force=force,
            batch_size=batch_size,
            database_batch_size=database_batch_size,
            failed_only=failed_only,
        )

    return result.asdict()
