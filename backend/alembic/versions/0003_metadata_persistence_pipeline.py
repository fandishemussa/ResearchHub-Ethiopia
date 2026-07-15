"""Add metadata persistence pipeline entities and indexes.

Revision ID: 0003_metadata_pipeline
Revises: 0002_storage_layer_indexes
Create Date: 2026-07-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_metadata_pipeline"
down_revision = "0002_storage_layer_indexes"
branch_labels = None
depends_on = None


def uuid_column() -> sa.Column:
    """Create a UUID primary key column."""

    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def timestamps() -> tuple[sa.Column, sa.Column]:
    """Return timestamp columns used by controlled vocabularies."""

    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def upgrade() -> None:
    """Create controlled metadata tables and publication matching columns."""

    op.create_table(
        "publication_types",
        uuid_column(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("normalized_name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        *timestamps(),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_publication_types_name", "publication_types", ["name"])
    op.create_index("ix_publication_types_normalized_name", "publication_types", ["normalized_name"])

    op.create_table(
        "licenses",
        uuid_column(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(500)),
        *timestamps(),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_licenses_name", "licenses", ["name"])
    op.create_index("ix_licenses_normalized_name", "licenses", ["normalized_name"])

    op.add_column("publications", sa.Column("normalized_title", sa.String(1000)))
    op.add_column(
        "publications",
        sa.Column("publication_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("publication_types.id")),
    )
    op.add_column(
        "publications",
        sa.Column("license_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("licenses.id")),
    )
    op.add_column("publications", sa.Column("source_urls", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")))
    op.add_column("publications", sa.Column("repository_datestamp", sa.DateTime(timezone=True)))
    op.add_column("publications", sa.Column("normalized_record", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")))

    op.create_index("ix_publications_normalized_title", "publications", ["normalized_title"])
    op.create_index("ix_publications_publication_type_id", "publications", ["publication_type_id"])
    op.create_index("ix_publications_license_id", "publications", ["license_id"])
    op.create_index("ix_publications_repository_datestamp", "publications", ["repository_datestamp"])
    op.create_index(
        "ix_publications_title_year_deleted",
        "publications",
        ["normalized_title", "publication_year", "is_deleted"],
    )


def downgrade() -> None:
    """Drop metadata pipeline schema additions."""

    op.drop_index("ix_publications_title_year_deleted", table_name="publications")
    op.drop_index("ix_publications_repository_datestamp", table_name="publications")
    op.drop_index("ix_publications_license_id", table_name="publications")
    op.drop_index("ix_publications_publication_type_id", table_name="publications")
    op.drop_index("ix_publications_normalized_title", table_name="publications")

    op.drop_column("publications", "normalized_record")
    op.drop_column("publications", "repository_datestamp")
    op.drop_column("publications", "source_urls")
    op.drop_column("publications", "license_id")
    op.drop_column("publications", "publication_type_id")
    op.drop_column("publications", "normalized_title")

    op.drop_index("ix_licenses_normalized_name", table_name="licenses")
    op.drop_index("ix_licenses_name", table_name="licenses")
    op.drop_table("licenses")

    op.drop_index("ix_publication_types_normalized_name", table_name="publication_types")
    op.drop_index("ix_publication_types_name", table_name="publication_types")
    op.drop_table("publication_types")
