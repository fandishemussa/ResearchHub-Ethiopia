"""Extend connectors as managed sources and add harvest observability.

Revision ID: 0009_source_management
Revises: 0008_ai_operations_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_source_management"
down_revision: str | None = "0008_ai_operations_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)
    connector_columns = [
        sa.Column("journal_id", uuid, sa.ForeignKey("journals.id")),
        sa.Column("description", sa.Text()),
        sa.Column("api_url", sa.String(500)),
        sa.Column("oai_endpoint", sa.String(500)),
        sa.Column("metadata_prefix", sa.String(80), nullable=False, server_default="oai_dc"),
        sa.Column("set_spec", sa.String(255)),
        sa.Column("supported_formats", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("last_health_check_at", timestamp),
        sa.Column("last_successful_harvest_at", timestamp),
        sa.Column("last_failed_harvest_at", timestamp),
        sa.Column("last_error", sa.Text()),
        sa.Column("consecutive_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_records_harvested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_active_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_deleted_records", sa.Integer(), nullable=False, server_default="0"),
    ]
    for column in connector_columns:
        op.add_column("connectors", column)
    for column in ("journal_id", "oai_endpoint", "status"):
        op.create_index(f"ix_connectors_{column}", "connectors", [column])

    job_columns = [
        sa.Column("job_type", sa.String(40), nullable=False, server_default="online_harvest"),
        sa.Column("mode", sa.String(30), nullable=False, server_default="full"),
        sa.Column("requested_by", uuid),
        sa.Column("completed_at", timestamp),
        sa.Column("cancelled_at", timestamp),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("total_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("resumption_token", sa.Text()),
        sa.Column("input_filename", sa.String(500)),
        sa.Column("input_file_checksum", sa.String(64)),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("result_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
    ]
    for column in job_columns:
        op.add_column("harvest_jobs", column)
    for column in ("job_type", "mode", "input_file_checksum"):
        op.create_index(f"ix_harvest_jobs_{column}", "harvest_jobs", [column])

    op.create_table(
        "harvest_failures",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "harvest_job_id",
            uuid,
            sa.ForeignKey("harvest_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(500)),
        sa.Column("record_index", sa.Integer()),
        sa.Column("error_type", sa.String(120), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("raw_record", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved_at", timestamp),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    for column in (
        "harvest_job_id",
        "external_id",
        "error_type",
        "retryable",
        "resolved",
        "created_at",
    ):
        op.create_index(f"ix_harvest_failures_{column}", "harvest_failures", [column])
    op.create_table(
        "import_files",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "harvest_job_id",
            uuid,
            sa.ForeignKey("harvest_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False, unique=True),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False, unique=True),
        sa.Column("uploaded_by", uuid),
        sa.Column("uploaded_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("validation_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    for column in ("harvest_job_id", "checksum", "validation_status"):
        op.create_index(f"ix_import_files_{column}", "import_files", [column])


def downgrade() -> None:
    op.drop_table("import_files")
    op.drop_table("harvest_failures")
    for column in ("input_file_checksum", "mode", "job_type"):
        op.drop_index(f"ix_harvest_jobs_{column}", table_name="harvest_jobs")
    for column in (
        "result_summary",
        "error_summary",
        "dry_run",
        "input_file_checksum",
        "input_filename",
        "resumption_token",
        "checkpoint",
        "failed_records",
        "skipped_records",
        "duplicate_records",
        "deleted_records",
        "unchanged_records",
        "updated_records",
        "created_records",
        "fetched_records",
        "total_records",
        "processed_pages",
        "total_pages",
        "duration_ms",
        "cancelled_at",
        "completed_at",
        "requested_by",
        "mode",
        "job_type",
    ):
        op.drop_column("harvest_jobs", column)
    for column in ("status", "oai_endpoint", "journal_id"):
        op.drop_index(f"ix_connectors_{column}", table_name="connectors")
    for column in (
        "total_deleted_records",
        "total_active_records",
        "total_records_harvested",
        "consecutive_failure_count",
        "last_error",
        "last_failed_harvest_at",
        "last_successful_harvest_at",
        "last_health_check_at",
        "status",
        "is_public",
        "supported_formats",
        "set_spec",
        "metadata_prefix",
        "oai_endpoint",
        "api_url",
        "description",
        "journal_id",
    ):
        op.drop_column("connectors", column)
