"""Database-backed harvest job lifecycle for managed sources."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.core.config import Settings
from researchhub.domain.schemas import SourceHarvestRequest
from researchhub.infrastructure.persistence.models import (
    Connector,
    HarvestFailure,
    HarvestJob,
    HarvestLog,
)

ACTIVE_STATUSES = {"pending", "queued", "running", "retrying"}


class HarvestOperationsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def queue(self, source_id: UUID, payload: SourceHarvestRequest) -> HarvestJob:
        # Serialize the short capacity-check/insert section across API replicas.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('researchhub:harvest-capacity'))")
        )
        source = await self.session.get(Connector, source_id, with_for_update=True)
        if source is None:
            raise LookupError("Source not found")
        if not source.enabled:
            raise ValueError("Disabled sources cannot be harvested")
        connector_type = source.connector_type.replace("-", "_")
        if connector_type not in {
            "oai_pmh",
            "dspace_oai",
            "ojs_oai",
            "dspace_discovery",
        }:
            raise ValueError(
                "Online harvesting is only available for OAI-PMH and DSpace Discovery sources"
            )
        # Normalize legacy/imported values such as ``oai-pmh`` so subsequent
        # harvests and API responses use the canonical SourceType spelling.
        if source.connector_type != connector_type:
            source.connector_type = connector_type
        active = await self.session.scalar(
            select(func.count(HarvestJob.id)).where(
                HarvestJob.connector_id == source_id,
                HarvestJob.status.in_(ACTIVE_STATUSES),
            )
        )
        if active:
            raise RuntimeError("A harvest is already active for this source")
        global_active = int(
            await self.session.scalar(
                select(func.count(HarvestJob.id)).where(
                    HarvestJob.status.in_(ACTIVE_STATUSES)
                )
            )
            or 0
        )
        if global_active >= self.settings.max_active_harvests_global:
            raise RuntimeError("Global harvest capacity is currently exhausted")
        mode = "dry_run" if payload.dry_run else payload.mode
        since = payload.from_date
        if mode == "incremental" and since is None and source.last_successful_harvest_at:
            since = source.last_successful_harvest_at.date()
        job = HarvestJob(
            connector_id=source_id,
            job_type="incremental_harvest" if mode == "incremental" else "online_harvest",
            mode=mode,
            status="queued",
            since=since,
            until=payload.until_date,
            dry_run=mode == "dry_run" or not payload.import_to_database,
            checkpoint={},
            metadata_json={
                "metadata_prefix": payload.metadata_prefix or source.metadata_prefix,
                "set_spec": payload.set_spec if payload.set_spec is not None else source.set_spec,
                "maximum_records": payload.maximum_records,
                "include_deleted_records": payload.include_deleted_records,
                "force": payload.force,
                "resume_from_checkpoint": payload.resume_from_checkpoint,
            },
        )
        self.session.add(job)
        await self.session.flush()
        self.session.add(
            HarvestLog(
                harvest_job_id=job.id,
                level="info",
                event="job_created",
                message=f"{mode} harvest queued",
                context={"source_id": str(source_id)},
            )
        )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def list(
        self, *, source_id: UUID | None = None, status: str | None = None, limit: int = 100
    ) -> list[HarvestJob]:
        statement = select(HarvestJob)
        if source_id:
            statement = statement.where(HarvestJob.connector_id == source_id)
        if status:
            statement = statement.where(HarvestJob.status == status)
        return list(
            (
                await self.session.scalars(
                    statement.order_by(HarvestJob.created_at.desc()).limit(limit)
                )
            ).all()
        )

    async def get(self, job_id: UUID) -> HarvestJob | None:
        return await self.session.get(HarvestJob, job_id)

    async def cancel(self, job_id: UUID) -> HarvestJob:
        job = await self.get(job_id)
        if job is None:
            raise LookupError("Harvest job not found")
        if job.status not in ACTIVE_STATUSES:
            raise ValueError("Only active harvest jobs can be cancelled")
        job.status = "cancelled"
        job.cancelled_at = datetime.now(UTC)
        self.session.add(
            HarvestLog(
                harvest_job_id=job.id,
                level="warning",
                event="job_cancelled",
                message="Harvest cancellation requested",
                context={},
            )
        )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def retry(self, job_id: UUID, *, failed_only: bool = False) -> HarvestJob:
        original = await self.get(job_id)
        if original is None:
            raise LookupError("Harvest job not found")
        if original.status in ACTIVE_STATUSES:
            raise ValueError("An active job cannot be retried")
        payload = SourceHarvestRequest(
            mode="resume" if original.checkpoint else original.mode,
            from_date=original.since,
            until_date=original.until,
            metadata_prefix=original.metadata_json.get("metadata_prefix"),
            set_spec=original.metadata_json.get("set_spec"),
            dry_run=original.dry_run,
            resume_from_checkpoint=bool(original.checkpoint),
        )
        job = await self.queue(original.connector_id, payload)
        job.job_type = "retry_failed" if failed_only else original.job_type
        job.status = "retrying"
        job.checkpoint = original.checkpoint
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def events(self, job_id: UUID) -> list[HarvestLog]:
        if await self.get(job_id) is None:
            raise LookupError("Harvest job not found")
        return list(
            (
                await self.session.scalars(
                    select(HarvestLog)
                    .where(HarvestLog.harvest_job_id == job_id)
                    .order_by(HarvestLog.created_at)
                )
            ).all()
        )

    async def failures(self, job_id: UUID) -> list[HarvestFailure]:
        if await self.get(job_id) is None:
            raise LookupError("Harvest job not found")
        return list(
            (
                await self.session.scalars(
                    select(HarvestFailure)
                    .where(HarvestFailure.harvest_job_id == job_id)
                    .order_by(HarvestFailure.created_at)
                )
            ).all()
        )
