"""Add concurrency constraints and high-traffic query indexes.

Revision ID: 0011_concurrency_indexes
Revises: 0010_authentication_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_concurrency_indexes"
down_revision: str | None = "0010_authentication_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_harvest_jobs_one_active_per_connector",
        "harvest_jobs",
        ["connector_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'queued', 'running', 'retrying')"
        ),
    )
    op.create_index(
        "ix_publications_active_updated_id",
        "publications",
        ["is_deleted", sa.text("updated_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_connectors_status_enabled_name",
        "connectors",
        ["status", "enabled", "name"],
    )
    op.create_index(
        "ix_refresh_sessions_user_revoked_expires",
        "refresh_sessions",
        ["user_id", "revoked_at", "expires_at"],
    )
    op.create_index(
        "ix_harvest_jobs_status_created",
        "harvest_jobs",
        ["status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    for index, table in (
        ("ix_harvest_jobs_status_created", "harvest_jobs"),
        ("ix_refresh_sessions_user_revoked_expires", "refresh_sessions"),
        ("ix_connectors_status_enabled_name", "connectors"),
        ("ix_publications_active_updated_id", "publications"),
        ("uq_harvest_jobs_one_active_per_connector", "harvest_jobs"),
    ):
        op.drop_index(index, table_name=table)
