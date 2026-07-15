"""Celery worker entrypoint for asynchronous harvesting and enrichment tasks."""

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from celery import Celery
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

from researchhub.application.document_indexer import index_pdf
from researchhub.application.embeddings import PublicationEmbeddingProcessor
from researchhub.application.harvest_store import SQLAlchemyHarvestStore
from researchhub.core.config import get_settings
from researchhub.infrastructure.persistence.models import Connector, HarvestJob
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


# ---------------------------------------------------------------------------
# Document indexing
# ---------------------------------------------------------------------------

@celery_app.task(
    name="researchhub.documents.index_file",
    queue="documents",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def index_document_file(
        self,
        file_path: str,
        source: str,
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

@celery_app.task(name="researchhub.healthcheck")
def healthcheck() -> str:
    """Return a simple worker health signal."""

    return "ok"


# ---------------------------------------------------------------------------
# Harvest tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="researchhub.harvest.run_config")
def run_harvest_config(
        config_path: str | None = None,
) -> dict[str, object]:
    """Run all enabled connectors from a JSON config path."""

    path = config_path or settings.harvest_config_path

    if not path:
        raise ValueError("No harvest config path configured")

    return _run_task(_run_all(path))


@celery_app.task(name="researchhub.harvest.run_connector")
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


@celery_app.task(name="researchhub.harvest.run_source")
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

        definition = HarvestConnectorDefinition(
            code=source.code,
            name=source.name,
            connector_type="oai-pmh",
            base_url=source.oai_endpoint or source.base_url or "",
            source_type=source.connector_type,
            metadata_prefix=str(
                job.metadata_json.get("metadata_prefix")
                or source.metadata_prefix
            ),
            set_spec=job.metadata_json.get("set_spec") or source.set_spec,
            from_date=job.since,
            until_date=job.until,
            connector_id=source.id,
            university_id=source.university_id,
            repository_id=source.repository_id,
            timeout_seconds=settings.harvest_request_timeout_seconds,
            max_retries=settings.harvest_max_retries,
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

    return report.asdict()


# ---------------------------------------------------------------------------
# Embedding tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="researchhub.embeddings.generate")
def generate_embeddings(
        source: str = "aau-etd",
        model: str | None = None,
        limit: int | None = None,
        force: bool = False,
        batch_size: int = 32,
        database_batch_size: int = 300,
) -> dict[str, object]:
    """Generate resumable publication embeddings."""

    return _run_task(
        _generate_embeddings(
            source=source,
            model=model or settings.embedding_model,
            limit=limit,
            force=force,
            batch_size=batch_size,
            database_batch_size=database_batch_size,
        )
    )


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
        source: str,
        model: str,
        limit: int | None,
        force: bool,
        batch_size: int,
        database_batch_size: int,
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
            limit=limit,
            force=force,
            batch_size=batch_size,
            database_batch_size=database_batch_size,
        )

    return result.asdict()