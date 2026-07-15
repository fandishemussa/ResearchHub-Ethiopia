"""Managed metadata sources and OAI-PMH connection testing."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from researchhub_harvester.connectors.base import ConnectorConfig
from researchhub_harvester.connectors.oai_pmh import OAIPMHConnector
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.domain.schemas import SourceCreate, SourceUpdate
from researchhub.infrastructure.persistence.models import (
    Connector,
    HarvestJob,
    HarvestLog,
    Journal,
    Publication,
    Repository,
    University,
)

OAI_TYPES = {"oai_pmh", "dspace_oai", "ojs_oai"}
SECRET_KEYS = {"api_key", "password", "secret", "token", "authorization"}


class SourceManagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        source_type: str | None = None,
        status: str | None = None,
        university_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Connector]:
        statement = select(Connector).where(Connector.status != "removed")
        if source_type:
            statement = statement.where(Connector.connector_type == source_type)
        if status:
            statement = statement.where(Connector.status == status)
        if university_id:
            statement = statement.where(Connector.university_id == university_id)
        return list(
            (
                await self.session.scalars(
                    statement.order_by(Connector.name).limit(limit).offset(offset)
                )
            ).all()
        )

    async def get(self, source_id: UUID) -> Connector | None:
        return await self.session.get(Connector, source_id)

    async def create(self, payload: SourceCreate) -> Connector:
        await self._validate_relations(
            payload.university_id, payload.repository_id, payload.journal_id
        )
        if payload.source_type in OAI_TYPES and payload.oai_endpoint is None:
            raise ValueError("An OAI endpoint is required for this source type")
        endpoint = str(payload.oai_endpoint) if payload.oai_endpoint else None
        conditions = [Connector.code == payload.slug]
        if endpoint:
            conditions.append(Connector.oai_endpoint == endpoint)
        existing = await self.session.scalar(select(Connector).where(or_(*conditions)))
        if existing is not None and existing.status != "removed":
            raise ValueError("A source with this slug or endpoint already exists")

        source = existing or Connector()
        source.code = payload.slug
        source.name = payload.name.strip()
        source.connector_type = payload.source_type
        source.base_url = str(payload.base_url) if payload.base_url else None
        source.api_url = str(payload.api_url) if payload.api_url else None
        source.oai_endpoint = endpoint
        source.university_id = payload.university_id
        source.repository_id = payload.repository_id
        source.journal_id = payload.journal_id
        source.description = payload.description
        source.metadata_prefix = payload.metadata_prefix
        source.set_spec = payload.set_spec
        source.supported_formats = payload.supported_formats
        source.config = _sanitize_for_storage(payload.connection_config)
        source.enabled = payload.is_active
        source.is_public = payload.is_public
        source.status = "active" if payload.is_active else "disabled"
        source.last_error = None
        source.consecutive_failure_count = 0
        if existing is None:
            self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def update(self, source_id: UUID, payload: SourceUpdate) -> Connector:
        source = await self.get(source_id)
        if source is None:
            raise LookupError("Source not found")
        values = payload.model_dump(exclude_unset=True)
        endpoint_changed = "oai_endpoint" in values
        prospective_endpoint = values.get("oai_endpoint", source.oai_endpoint)
        if source.connector_type in OAI_TYPES and prospective_endpoint is None:
            raise ValueError("An OAI endpoint is required for this source type")
        if prospective_endpoint is not None:
            endpoint = str(prospective_endpoint)
            duplicate = await self.session.scalar(
                select(Connector.id).where(
                    Connector.oai_endpoint == endpoint,
                    Connector.id != source_id,
                    Connector.status != "removed",
                )
            )
            if duplicate is not None:
                raise ValueError("A source with this endpoint already exists")
        aliases = {"is_active": "enabled", "connection_config": "config"}
        for key, value in values.items():
            column = aliases.get(key, key)
            if key in {"base_url", "api_url", "oai_endpoint"} and value is not None:
                value = str(value)
            if key == "connection_config" and value is not None:
                value = _sanitize_for_storage(value)
            setattr(source, column, value)
        if "is_active" in values:
            source.status = "active" if source.enabled else "disabled"
        elif endpoint_changed:
            source.status = "unknown" if source.enabled else "disabled"
        if endpoint_changed:
            source.last_error = None
            source.consecutive_failure_count = 0
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def delete(self, source_id: UUID) -> bool:
        source = await self.get(source_id)
        if source is None:
            return False
        active = await self.session.scalar(
            select(func.count(HarvestJob.id)).where(
                HarvestJob.connector_id == source_id,
                HarvestJob.status.in_(["pending", "queued", "running", "retrying"]),
            )
        )
        if active:
            raise RuntimeError("A source with an active harvest job cannot be deleted")
        job_count = int(
            await self.session.scalar(
                select(func.count(HarvestJob.id)).where(HarvestJob.connector_id == source_id)
            )
            or 0
        )
        if job_count == 0:
            await self.session.delete(source)
        else:
            # Preserve the connector key required by historical harvest records. A
            # later create with the same slug or endpoint restores this row.
            source.enabled = False
            source.is_public = False
            source.status = "removed"
            source.config = {}
            source.last_error = None
        await self.session.commit()
        return True

    async def set_enabled(self, source_id: UUID, enabled: bool) -> Connector:
        source = await self.get(source_id)
        if source is None:
            raise LookupError("Source not found")
        source.enabled = enabled
        source.status = "active" if enabled else "disabled"
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def statistics(self, source_id: UUID) -> dict[str, int]:
        source = await self.get(source_id)
        if source is None:
            raise LookupError("Source not found")
        total = int(
            await self.session.scalar(
                select(func.count(Publication.id)).where(Publication.source == source.code)
            )
            or 0
        )
        deleted = int(
            await self.session.scalar(
                select(func.count(Publication.id)).where(
                    Publication.source == source.code, Publication.is_deleted.is_(True)
                )
            )
            or 0
        )
        return {
            "total": total,
            "active": total - deleted,
            "deleted": deleted,
            "harvested": source.total_records_harvested,
        }

    async def history(self, source_id: UUID, limit: int = 50) -> list[HarvestJob]:
        if await self.get(source_id) is None:
            raise LookupError("Source not found")
        return list(
            (
                await self.session.scalars(
                    select(HarvestJob)
                    .where(HarvestJob.connector_id == source_id)
                    .order_by(HarvestJob.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def test_saved(self, source_id: UUID) -> dict[str, Any]:
        source = await self.get(source_id)
        if source is None:
            raise LookupError("Source not found")
        result = await test_source_configuration(
            source.connector_type,
            source.code,
            source.name,
            source.oai_endpoint or source.base_url,
            source.metadata_prefix,
            source.set_spec,
        )
        now = datetime.now(UTC)
        source.last_health_check_at = now
        source.status = (
            "active"
            if result["success"] and source.enabled
            else "disabled"
            if not source.enabled
            else "unavailable"
        )
        source.last_error = None if result["success"] else "; ".join(result["errors"])
        source.consecutive_failure_count = (
            0 if result["success"] else source.consecutive_failure_count + 1
        )
        job = HarvestJob(
            connector_id=source.id,
            job_type="connection_test",
            mode="dry_run",
            dry_run=True,
            status="completed" if result["success"] else "failed",
            started_at=now,
            completed_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            result_summary=result,
            error_summary={"errors": result["errors"]},
        )
        self.session.add(job)
        await self.session.flush()
        self.session.add(
            HarvestLog(
                harvest_job_id=job.id,
                level="info" if result["success"] else "error",
                event="connection_succeeded" if result["success"] else "connection_failed",
                message="Source connection test completed",
                context=result,
            )
        )
        await self.session.commit()
        return result

    async def _validate_relations(
        self, university_id: UUID, repository_id: UUID | None, journal_id: UUID | None
    ) -> None:
        if await self.session.get(University, university_id) is None:
            raise ValueError("University not found")
        if repository_id:
            repository = await self.session.get(Repository, repository_id)
            if repository is None or repository.university_id != university_id:
                raise ValueError("Repository does not belong to the selected university")
        if journal_id:
            journal = await self.session.get(Journal, journal_id)
            if journal is None or journal.university_id not in (None, university_id):
                raise ValueError("Journal does not belong to the selected university")


async def test_source_configuration(
    source_type: str,
    code: str,
    name: str,
    endpoint: str | None,
    metadata_prefix: str,
    set_spec: str | None,
) -> dict[str, Any]:
    source_type = source_type.replace("-", "_")
    if source_type not in OAI_TYPES:
        return {
            "success": True,
            "response_time_ms": 0,
            "repository_name": name,
            "protocol_version": None,
            "admin_emails": [],
            "earliest_datestamp": None,
            "deletion_policy": None,
            "supported_metadata_formats": [],
            "supported_sets": [],
            "sample_record_count": 0,
            "warnings": ["Connection testing is not implemented for this source type yet."],
            "errors": [],
        }
    if not endpoint:
        raise ValueError("An OAI endpoint is required")
    connector = OAIPMHConnector(
        ConnectorConfig(
            code=code,
            name=name,
            base_url=endpoint,
            source_type=source_type,
            metadata_prefix=metadata_prefix,
            set_spec=set_spec,
        )
    )
    started = perf_counter()
    try:
        identify = await asyncio.to_thread(connector.identify_sync)
        formats = await asyncio.to_thread(connector.list_metadata_formats_sync)
        prefixes = [item["metadataPrefix"] for item in formats]
        errors = (
            []
            if metadata_prefix in prefixes
            else [f"Metadata prefix '{metadata_prefix}' is not supported"]
        )
        return {
            "success": not errors,
            "response_time_ms": round((perf_counter() - started) * 1000),
            "repository_name": identify.get("repositoryName"),
            "protocol_version": identify.get("protocolVersion"),
            "admin_emails": [identify["adminEmail"]] if identify.get("adminEmail") else [],
            "earliest_datestamp": identify.get("earliestDatestamp"),
            "deletion_policy": identify.get("deletedRecord"),
            "supported_metadata_formats": prefixes,
            "supported_sets": [],
            "sample_record_count": 0,
            "warnings": [],
            "errors": errors,
        }
    except Exception as exc:
        return {
            "success": False,
            "response_time_ms": round((perf_counter() - started) * 1000),
            "repository_name": None,
            "protocol_version": None,
            "admin_emails": [],
            "earliest_datestamp": None,
            "deletion_policy": None,
            "supported_metadata_formats": [],
            "supported_sets": [],
            "sample_record_count": 0,
            "warnings": [],
            "errors": [str(exc)],
        }


def _sanitize_for_storage(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key.casefold() not in SECRET_KEYS}
