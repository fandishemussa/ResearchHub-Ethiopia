"""Add storage-layer filtering indexes.

Revision ID: 0002_storage_layer_indexes
Revises: 0001_initial_schema
Create Date: 2026-07-11
"""

from alembic import op

revision = "0002_storage_layer_indexes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create composite indexes used by repository filters and pagination."""

    op.create_index(
        "ix_repositories_university_platform_active",
        "repositories",
        ["university_id", "platform", "is_active"],
    )
    op.create_index(
        "ix_publications_repo_year_lang_deleted",
        "publications",
        ["repository_id", "publication_year", "language", "is_deleted"],
    )
    op.create_index(
        "ix_publications_source_external_deleted",
        "publications",
        ["source", "external_id", "is_deleted"],
    )
    op.create_index(
        "ix_authors_university_normalized_name",
        "authors",
        ["university_id", "normalized_name"],
    )
    op.create_index(
        "ix_keywords_vocabulary_normalized_term",
        "keywords",
        ["vocabulary", "normalized_term"],
    )
    op.create_index(
        "ix_harvest_jobs_connector_status_started",
        "harvest_jobs",
        ["connector_id", "status", "started_at"],
    )


def downgrade() -> None:
    """Drop repository-filtering indexes."""

    op.drop_index("ix_harvest_jobs_connector_status_started", table_name="harvest_jobs")
    op.drop_index("ix_keywords_vocabulary_normalized_term", table_name="keywords")
    op.drop_index("ix_authors_university_normalized_name", table_name="authors")
    op.drop_index("ix_publications_source_external_deleted", table_name="publications")
    op.drop_index("ix_publications_repo_year_lang_deleted", table_name="publications")
    op.drop_index("ix_repositories_university_platform_active", table_name="repositories")
