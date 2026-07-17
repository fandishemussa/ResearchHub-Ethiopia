"""Secure metadata-file upload, preview, and confirmed database import."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from researchhub_harvester.connectors.base import ConnectorConfig, NormalizedPublication
from researchhub_harvester.connectors.oai_pmh import OAIPMHConnector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.application.harvest_persistence import (
    HarvestPersistenceContext,
    HarvestPersistenceService,
)
from researchhub.core.config import Settings
from researchhub.infrastructure.persistence.models import (
    Connector,
    HarvestFailure,
    HarvestJob,
    HarvestLog,
    ImportFile,
)

ALLOWED_MIME = {
    "xml": {"application/xml", "text/xml", "application/octet-stream"},
    "json": {"application/json", "text/json", "application/octet-stream"},
    "csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"},
}


class ImportOperationsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def upload(
        self, source_id: UUID, file_format: str, original_name: str, mime_type: str, content: bytes
    ) -> HarvestJob:
        source = await self.session.get(Connector, source_id)
        if source is None:
            raise LookupError("Source not found")
        if file_format not in ALLOWED_MIME:
            raise ValueError("Unsupported import format")
        extension = Path(original_name).suffix.casefold().lstrip(".")
        if extension != file_format:
            raise ValueError(f"Expected a .{file_format} file")
        if mime_type not in ALLOWED_MIME[file_format]:
            raise ValueError("Unsupported file MIME type")
        if not content:
            raise ValueError("Uploaded file is empty")
        if len(content) > self.settings.import_max_file_size_mb * 1024 * 1024:
            raise ValueError("Uploaded file exceeds the configured size limit")
        checksum = sha256(content).hexdigest()
        if await self.session.scalar(select(ImportFile.id).where(ImportFile.checksum == checksum)):
            raise ValueError("This file has already been uploaded")
        records, validation_errors, total_rows = _parse_records_with_errors(
            content, file_format, source
        )
        if not records:
            detail = validation_errors[0]["message"] if validation_errors else "No records found"
            raise ValueError(f"The file contains no valid records. {detail}")
        storage = Path(self.settings.import_storage_path).resolve()
        storage.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}.{file_format}"
        path = (storage / stored_name).resolve()
        if storage not in path.parents:
            raise ValueError("Invalid storage path")
        path.write_bytes(content)
        job = HarvestJob(
            connector_id=source_id,
            job_type=f"{file_format}_import",
            mode="dry_run",
            status="pending",
            input_filename=original_name,
            input_file_checksum=checksum,
            dry_run=True,
            total_records=total_rows,
            skipped_records=len(validation_errors),
            result_summary={
                "preview_ready": True,
                "valid_records": len(records),
                "invalid_records": len(validation_errors),
            },
        )
        self.session.add(job)
        await self.session.flush()
        self.session.add(
            ImportFile(
                harvest_job_id=job.id,
                original_filename=Path(original_name).name,
                stored_filename=stored_name,
                storage_path=str(path),
                mime_type=mime_type,
                file_size=len(content),
                checksum=checksum,
                validation_status="valid" if not validation_errors else "valid_with_warnings",
                validation_errors=validation_errors[:1000],
            )
        )
        self.session.add(
            HarvestLog(
                harvest_job_id=job.id,
                level="info",
                event="import_started",
                message="Import file validated and stored",
                context={
                    "format": file_format,
                    "records": total_rows,
                    "valid_records": len(records),
                    "invalid_records": len(validation_errors),
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(job)
        from researchhub.application.worker import celery_app

        celery_app.send_task(
            "researchhub.embeddings.generate",
            kwargs={"source": source.code},
            task_id=f"import-embeddings-{job.id}",
        )
        return job

    async def preview(self, job_id: UUID) -> dict[str, Any]:
        job, source, import_file = await self._load(job_id)
        records, validation_errors, total_rows = _parse_records_with_errors(
            Path(import_file.storage_path).read_bytes(),
            Path(import_file.stored_filename).suffix[1:],
            source,
        )
        active = sum(not item.is_deleted for item in records)
        deleted = len(records) - active
        preview = {
            "detected_format": Path(import_file.stored_filename).suffix[1:],
            "total_records": total_rows,
            "valid_records": len(records),
            "invalid_records": len(validation_errors),
            "active_records": active,
            "deleted_records": deleted,
            "likely_creates": active,
            "likely_updates": 0,
            "possible_duplicates": 0,
            "sample_records": [
                {
                    "external_id": item.external_id,
                    "title": item.title,
                    "publication_year": item.publication_year,
                    "is_deleted": item.is_deleted,
                }
                for item in records[: self.settings.import_preview_limit]
            ],
            "validation_errors": validation_errors[:100],
        }
        job.result_summary = {**job.result_summary, "preview": preview}
        await self.session.commit()
        return preview

    async def confirm(self, job_id: UUID) -> HarvestJob:
        job, source, import_file = await self._load(job_id, for_update=True)
        if job.status not in {"pending", "failed", "partially_completed"}:
            raise ValueError("Import job cannot be confirmed in its current state")
        records, validation_errors, total_rows = _parse_records_with_errors(
            Path(import_file.storage_path).read_bytes(),
            Path(import_file.stored_filename).suffix[1:],
            source,
        )
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.dry_run = False
        self.session.add(
            HarvestLog(
                harvest_job_id=job.id,
                level="info",
                event="import_started",
                message="Database import started",
                context={"records": len(records)},
            )
        )
        await self.session.commit()
        result = await HarvestPersistenceService(self.session).persist_many(
            records,
            HarvestPersistenceContext(
                source=source.code,
                source_type=source.connector_type,
                university_id=source.university_id,
                repository_id=source.repository_id,
                repository_name=source.name,
                repository_base_url=source.base_url or source.oai_endpoint,
                connector_code=source.code,
            ),
        )
        job.created_records = result.created_count
        job.updated_records = result.updated_count
        job.unchanged_records = result.unchanged_count
        job.deleted_records = result.deleted_count
        job.duplicate_records = result.duplicate_count
        job.failed_records = result.failed_count
        job.skipped_records = len(validation_errors)
        job.fetched_records = len(records)
        job.total_records = total_rows
        job.status = "completed" if not result.failed_count else "partially_completed"
        job.completed_at = datetime.now(UTC)
        job.finished_at = job.completed_at
        job.result_summary = {
            **result.asdict(),
            "validation_errors": validation_errors[:1000],
            "skipped_invalid_records": len(validation_errors),
        }
        import_file.validation_status = "processed"
        for index, error in enumerate(result.errors):
            self.session.add(
                HarvestFailure(
                    harvest_job_id=job.id,
                    external_id=error.get("identifier"),
                    record_index=index,
                    error_type="persistence_error",
                    error_message=str(error.get("error")),
                    raw_record={},
                    retryable=True,
                )
            )
        self.session.add(
            HarvestLog(
                harvest_job_id=job.id,
                level="info",
                event="import_completed",
                message="Database import completed",
                context=result.asdict(),
            )
        )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def cancel(self, job_id: UUID) -> HarvestJob:
        job = await self.session.get(HarvestJob, job_id)
        if job is None:
            raise LookupError("Import job not found")
        if job.status not in {"pending", "queued"}:
            raise ValueError("Only pending imports can be cancelled")
        job.status = "cancelled"
        job.cancelled_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def _load(
        self, job_id: UUID, *, for_update: bool = False
    ) -> tuple[HarvestJob, Connector, ImportFile]:
        job = await self.session.get(HarvestJob, job_id, with_for_update=for_update)
        if job is None:
            raise LookupError("Import job not found")
        source = await self.session.get(Connector, job.connector_id)
        file = await self.session.scalar(
            select(ImportFile).where(ImportFile.harvest_job_id == job_id)
        )
        if source is None or file is None:
            raise LookupError("Import source or file not found")
        return job, source, file


def _parse_records(
    content: bytes, file_format: str, source: Connector
) -> list[NormalizedPublication]:
    text = content.decode("utf-8-sig")
    if file_format == "xml":
        connector = OAIPMHConnector(
            ConnectorConfig(
                code=source.code,
                name=source.name,
                base_url=source.oai_endpoint or source.base_url or "http://invalid",
                source_type=source.connector_type,
                metadata_prefix=source.metadata_prefix,
            )
        )
        return connector.normalize_xml(text)
    if file_format == "json":
        payload = json.loads(text)
        rows = (
            payload
            if isinstance(payload, list)
            else payload.get("records", [payload])
            if isinstance(payload, dict)
            else []
        )
    elif file_format == "csv":
        rows = list(csv.DictReader(StringIO(text)))
    else:
        raise ValueError("Unsupported import format")
    return [_normalize_mapping(row, source) for row in rows]


def _parse_records_with_errors(
    content: bytes, file_format: str, source: Connector
) -> tuple[list[NormalizedPublication], list[dict[str, Any]], int]:
    if file_format == "xml":
        xml_records = _parse_records(content, file_format, source)
        return xml_records, [], len(xml_records)
    text = content.decode("utf-8-sig")
    if file_format == "json":
        payload = json.loads(text)
        rows = (
            payload
            if isinstance(payload, list)
            else payload.get("records", payload.get("items", [payload]))
            if isinstance(payload, dict)
            else []
        )
    elif file_format == "csv":
        rows = list(csv.DictReader(StringIO(text)))
    else:
        raise ValueError("Unsupported import format")
    if not isinstance(rows, list):
        raise ValueError("The JSON records or items field must be an array")
    records: list[NormalizedPublication] = []
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append({"record_index": index, "message": "Record is not an object"})
            continue
        try:
            records.append(_normalize_mapping(row, source))
        except (TypeError, ValueError) as exc:
            errors.append({"record_index": index, "message": str(exc)})
    return records, errors, len(rows)


def _normalize_mapping(row: dict[str, Any], source: Connector) -> NormalizedPublication:
    metadata_value = row.get("metadata")
    metadata: dict[str, Any] = metadata_value if isinstance(metadata_value, dict) else {}

    def raw_values(*keys: str) -> list[str]:
        for key in keys:
            value = row.get(key)
            if value in (None, "", []):
                value = metadata.get(key)
            if value in (None, "", []):
                continue
            items = value if isinstance(value, list) else [value]
            values = []
            for item in items:
                if isinstance(item, dict):
                    item = item.get("value") or item.get("text") or item.get("name")
                text_value = str(item or "").strip()
                if text_value:
                    values.append(text_value)
            if values:
                return values
        return []

    title_values = raw_values("title", "dc.title", "name")
    title = title_values[0] if title_values else ""
    if not title:
        raise ValueError("A record is missing its title")

    def values(key: str) -> list[str]:
        mapped_keys = {
            "authors": ("authors", "dc.contributor.author", "dc.creator"),
            "affiliations": ("affiliations", "dc.contributor.advisor"),
            "keywords": ("keywords", "dc.subject"),
            "subjects": ("subjects", "dc.subject"),
        }
        direct = raw_values(*mapped_keys.get(key, (key,)))
        if direct:
            if isinstance(row.get(key), str):
                return [
                    item.strip()
                    for item in str(row[key]).replace(";", ",").split(",")
                    if item.strip()
                ]
            return direct
        value = row.get(key, [])
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [
            item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()
        ]

    def first_value(*keys: str) -> str | None:
        candidates = raw_values(*keys)
        return candidates[0] if candidates else None

    date_values = raw_values("publication_year", "year", "publication_date", "dc.date.issued")
    year_text = date_values[0] if date_values else ""
    year = int(year_text[:4]) if year_text[:4].isdigit() else None
    now = datetime.now(UTC)
    url = (raw_values("article_url", "url", "landing_page_url", "dc.identifier.uri") or [""])[
        0
    ] or None
    return NormalizedPublication(
        external_id=str(
            row.get("external_id") or row.get("uuid") or row.get("handle") or ""
        ).strip()
        or None,
        title=title,
        abstract=first_value("abstract", "dc.description.abstract"),
        authors=values("authors"),
        affiliations=values("affiliations"),
        journal=str(row.get("journal") or row.get("journal_name") or "").strip() or None,
        publisher=first_value("publisher", "dc.publisher"),
        publication_date=date(year, 1, 1) if year else None,
        publication_year=year,
        keywords=values("keywords") or values("subjects"),
        subjects=values("subjects"),
        language=first_value("language", "languages", "dc.language", "dc.language.iso"),
        doi=first_value("doi", "dc.identifier.doi"),
        orcid=None,
        issn=None,
        isbn=None,
        license=str(row.get("rights") or "").strip() or None,
        article_url=url,
        pdf_url=str(row.get("pdf_url") or "").strip() or None,
        repository=source.name,
        repository_identifier=str(row.get("external_id") or "").strip() or None,
        source=source.code,
        source_type=source.connector_type,
        harvested_at=now,
        updated_at=now,
        quality_score=0.0,
        is_deleted=bool(row.get("is_deleted", False)),
        raw_record=row,
    )
