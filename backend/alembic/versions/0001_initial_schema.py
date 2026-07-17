"""Create normalized research metadata schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-11
"""

from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def uuid_column() -> sa.Column[Any]:
    """Create a PostgreSQL UUID primary key column with database-side defaults."""

    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def timestamps() -> Iterable[sa.Column[Any]]:
    """Shared timestamp columns for mutable tables."""

    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    """Create the first version of the ResearchHub database schema."""

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "universities",
        uuid_column(),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(80), nullable=False, server_default="Ethiopia"),
        sa.Column("city", sa.String(120)),
        sa.Column("website_url", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *timestamps(),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_universities_code", "universities", ["code"])
    op.create_index("ix_universities_country", "universities", ["country"])
    op.create_index("ix_universities_is_active", "universities", ["is_active"])

    op.create_table(
        "faculties",
        uuid_column(),
        sa.Column(
            "university_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("universities.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(60)),
        *timestamps(),
        sa.UniqueConstraint("university_id", "name"),
    )
    op.create_index("ix_faculties_university_id", "faculties", ["university_id"])
    op.create_index("ix_faculties_name", "faculties", ["name"])

    op.create_table(
        "departments",
        uuid_column(),
        sa.Column(
            "university_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("universities.id"),
            nullable=False,
        ),
        sa.Column("faculty_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("faculties.id")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(60)),
        *timestamps(),
        sa.UniqueConstraint("university_id", "name"),
    )
    op.create_index("ix_departments_university_id", "departments", ["university_id"])
    op.create_index("ix_departments_faculty_id", "departments", ["faculty_id"])
    op.create_index("ix_departments_name", "departments", ["name"])

    op.create_table(
        "repositories",
        uuid_column(),
        sa.Column(
            "university_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("universities.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(80), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("oai_endpoint", sa.String(500)),
        sa.Column(
            "metadata_formats",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_harvested_at", sa.DateTime(timezone=True)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *timestamps(),
        sa.UniqueConstraint("university_id", "name"),
    )
    op.create_index("ix_repositories_university_id", "repositories", ["university_id"])
    op.create_index("ix_repositories_platform", "repositories", ["platform"])
    op.create_index("ix_repositories_is_active", "repositories", ["is_active"])

    op.create_table(
        "journals",
        uuid_column(),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universities.id")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255)),
        sa.Column("issn", sa.String(20)),
        sa.Column("eissn", sa.String(20)),
        sa.Column("publisher", sa.String(255)),
        sa.Column("url", sa.String(500)),
        *timestamps(),
    )
    op.create_index("ix_journals_university_id", "journals", ["university_id"])
    op.create_index("ix_journals_name", "journals", ["name"])
    op.create_index("ix_journals_normalized_name", "journals", ["normalized_name"])
    op.create_index("ix_journals_issn", "journals", ["issn"])
    op.create_index("ix_journals_eissn", "journals", ["eissn"])

    op.create_table(
        "authors",
        uuid_column(),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255)),
        sa.Column("orcid", sa.String(19)),
        sa.Column("email", sa.String(255)),
        sa.Column("affiliation", sa.String(500)),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universities.id")),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id")),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *timestamps(),
        sa.UniqueConstraint("orcid"),
    )
    op.create_index("ix_authors_full_name", "authors", ["full_name"])
    op.create_index("ix_authors_normalized_name", "authors", ["normalized_name"])
    op.create_index("ix_authors_orcid", "authors", ["orcid"])
    op.create_index("ix_authors_university_id", "authors", ["university_id"])
    op.create_index("ix_authors_department_id", "authors", ["department_id"])

    op.create_table(
        "organizations",
        uuid_column(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255)),
        sa.Column("type", sa.String(80)),
        sa.Column("country", sa.String(80)),
        sa.Column("ror_id", sa.String(80)),
        sa.Column("url", sa.String(500)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *timestamps(),
        sa.UniqueConstraint("ror_id"),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])
    op.create_index("ix_organizations_normalized_name", "organizations", ["normalized_name"])
    op.create_index("ix_organizations_type", "organizations", ["type"])
    op.create_index("ix_organizations_country", "organizations", ["country"])

    op.create_table(
        "publications",
        uuid_column(),
        sa.Column("external_id", sa.String(500)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text()),
        sa.Column(
            "affiliations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("journal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journals.id")),
        sa.Column("publisher", sa.String(255)),
        sa.Column("publication_date", sa.Date()),
        sa.Column("publication_year", sa.Integer()),
        sa.Column(
            "subjects", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("language", sa.String(20)),
        sa.Column("doi", sa.String(255)),
        sa.Column("issn", sa.String(20)),
        sa.Column("isbn", sa.String(32)),
        sa.Column("license", sa.String(255)),
        sa.Column("article_url", sa.String(1000)),
        sa.Column("pdf_url", sa.String(1000)),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id")),
        sa.Column("repository_identifier", sa.String(500)),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("harvested_at", sa.DateTime(timezone=True)),
        sa.Column("quality_score", sa.Numeric(5, 2)),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "raw_record", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("search_vector", postgresql.TSVECTOR()),
        *timestamps(),
        sa.UniqueConstraint("source", "external_id"),
        sa.UniqueConstraint("doi"),
    )
    for column in [
        "external_id",
        "journal_id",
        "publisher",
        "publication_year",
        "language",
        "doi",
        "issn",
        "isbn",
        "repository_id",
        "repository_identifier",
        "source",
        "source_type",
        "harvested_at",
        "is_deleted",
    ]:
        op.create_index(f"ix_publications_{column}", "publications", [column])
    op.create_index(
        "ix_publications_source_type_year", "publications", ["source_type", "publication_year"]
    )
    op.create_index("ix_publications_quality_score", "publications", ["quality_score"])
    op.create_index(
        "ix_publications_search_vector", "publications", ["search_vector"], postgresql_using="gin"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION researchhub_publication_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
          NEW.search_vector :=
            to_tsvector('simple', unaccent(coalesce(NEW.title, '') || ' ' || coalesce(NEW.abstract, '')));
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_publications_search_vector
        BEFORE INSERT OR UPDATE OF title, abstract
        ON publications
        FOR EACH ROW EXECUTE FUNCTION researchhub_publication_search_vector_update()
        """
    )

    op.create_table(
        "publication_authors",
        uuid_column(),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id"),
            nullable=False,
        ),
        sa.Column(
            "author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authors.id"), nullable=False
        ),
        sa.Column("author_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("affiliation", sa.String(500)),
        sa.Column("orcid", sa.String(19)),
        *timestamps(),
        sa.UniqueConstraint("publication_id", "author_id"),
    )
    op.create_index(
        "ix_publication_authors_publication_id", "publication_authors", ["publication_id"]
    )
    op.create_index("ix_publication_authors_author_id", "publication_authors", ["author_id"])
    op.create_index("ix_publication_authors_orcid", "publication_authors", ["orcid"])

    op.create_table(
        "keywords",
        uuid_column(),
        sa.Column("term", sa.String(255), nullable=False),
        sa.Column("normalized_term", sa.String(255), nullable=False),
        sa.Column("vocabulary", sa.String(120)),
        *timestamps(),
        sa.UniqueConstraint("term"),
    )
    op.create_index("ix_keywords_term", "keywords", ["term"])
    op.create_index("ix_keywords_normalized_term", "keywords", ["normalized_term"])

    op.create_table(
        "publication_keywords",
        uuid_column(),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id"),
            nullable=False,
        ),
        sa.Column(
            "keyword_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("keywords.id"),
            nullable=False,
        ),
        sa.Column("relevance_score", sa.Numeric(5, 4)),
        *timestamps(),
        sa.UniqueConstraint("publication_id", "keyword_id"),
    )
    op.create_index(
        "ix_publication_keywords_publication_id", "publication_keywords", ["publication_id"]
    )
    op.create_index("ix_publication_keywords_keyword_id", "publication_keywords", ["keyword_id"])

    op.create_table(
        "datasets",
        uuid_column(),
        sa.Column(
            "publication_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("publications.id")
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("doi", sa.String(255)),
        sa.Column("url", sa.String(1000)),
        sa.Column("repository", sa.String(255)),
        sa.Column("license", sa.String(255)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *timestamps(),
        sa.UniqueConstraint("doi"),
    )
    op.create_index("ix_datasets_publication_id", "datasets", ["publication_id"])
    op.create_index("ix_datasets_doi", "datasets", ["doi"])

    op.create_table(
        "research_projects",
        uuid_column(),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universities.id")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("funder_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id")),
        sa.Column(
            "principal_investigator_author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("authors.id"),
        ),
        sa.Column("status", sa.String(80)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *timestamps(),
    )
    op.create_index("ix_research_projects_university_id", "research_projects", ["university_id"])
    op.create_index("ix_research_projects_title", "research_projects", ["title"])
    op.create_index("ix_research_projects_funder_id", "research_projects", ["funder_id"])
    op.create_index(
        "ix_research_projects_principal_investigator_author_id",
        "research_projects",
        ["principal_investigator_author_id"],
    )
    op.create_index("ix_research_projects_status", "research_projects", ["status"])

    op.create_table(
        "citations",
        uuid_column(),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id"),
            nullable=False,
        ),
        sa.Column("citing_doi", sa.String(255)),
        sa.Column("citing_title", sa.Text()),
        sa.Column("citing_source", sa.String(120)),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *timestamps(),
    )
    op.create_index("ix_citations_publication_id", "citations", ["publication_id"])
    op.create_index("ix_citations_citing_doi", "citations", ["citing_doi"])
    op.create_index("ix_citations_citing_source", "citations", ["citing_source"])
    op.create_index("ix_citations_observed_at", "citations", ["observed_at"])

    op.create_table(
        "connectors",
        uuid_column(),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("connector_type", sa.String(80), nullable=False),
        sa.Column("base_url", sa.String(500)),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universities.id")),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id")),
        sa.Column(
            "config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("schedule", sa.String(120)),
        sa.Column("last_cursor", sa.Text()),
        sa.Column("last_harvested_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_connectors_code", "connectors", ["code"])
    op.create_index("ix_connectors_connector_type", "connectors", ["connector_type"])
    op.create_index("ix_connectors_university_id", "connectors", ["university_id"])
    op.create_index("ix_connectors_repository_id", "connectors", ["repository_id"])
    op.create_index("ix_connectors_enabled", "connectors", ["enabled"])

    op.create_table(
        "harvest_jobs",
        uuid_column(),
        sa.Column(
            "connector_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connectors.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(40), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("since", sa.Date()),
        sa.Column("until", sa.Date()),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cursor", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *timestamps(),
    )
    op.create_index("ix_harvest_jobs_connector_id", "harvest_jobs", ["connector_id"])
    op.create_index("ix_harvest_jobs_status", "harvest_jobs", ["status"])
    op.create_index("ix_harvest_jobs_started_at", "harvest_jobs", ["started_at"])
    op.create_index("ix_harvest_jobs_finished_at", "harvest_jobs", ["finished_at"])

    op.create_table(
        "harvest_logs",
        uuid_column(),
        sa.Column(
            "harvest_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("harvest_jobs.id"),
            nullable=False,
        ),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("event", sa.String(120), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_harvest_logs_harvest_job_id", "harvest_logs", ["harvest_job_id"])
    op.create_index("ix_harvest_logs_level", "harvest_logs", ["level"])
    op.create_index("ix_harvest_logs_event", "harvest_logs", ["event"])
    op.create_index("ix_harvest_logs_created_at", "harvest_logs", ["created_at"])

    op.create_table(
        "metadata_history",
        uuid_column(),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("field_name", sa.String(120), nullable=False),
        sa.Column("old_value", postgresql.JSONB()),
        sa.Column("new_value", postgresql.JSONB()),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("changed_by", sa.String(120)),
    )
    op.create_index("ix_metadata_history_publication_id", "metadata_history", ["publication_id"])
    op.create_index("ix_metadata_history_source", "metadata_history", ["source"])
    op.create_index("ix_metadata_history_field_name", "metadata_history", ["field_name"])
    op.create_index("ix_metadata_history_changed_at", "metadata_history", ["changed_at"])

    op.create_table(
        "quality_reports",
        uuid_column(),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id"),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "missing_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.create_index("ix_quality_reports_publication_id", "quality_reports", ["publication_id"])
    op.create_index("ix_quality_reports_generated_at", "quality_reports", ["generated_at"])


def downgrade() -> None:
    """Drop the first version of the schema."""

    op.drop_index("ix_quality_reports_generated_at", table_name="quality_reports")
    op.drop_index("ix_quality_reports_publication_id", table_name="quality_reports")
    op.drop_table("quality_reports")

    op.drop_index("ix_metadata_history_changed_at", table_name="metadata_history")
    op.drop_index("ix_metadata_history_field_name", table_name="metadata_history")
    op.drop_index("ix_metadata_history_source", table_name="metadata_history")
    op.drop_index("ix_metadata_history_publication_id", table_name="metadata_history")
    op.drop_table("metadata_history")

    op.drop_index("ix_harvest_logs_created_at", table_name="harvest_logs")
    op.drop_index("ix_harvest_logs_event", table_name="harvest_logs")
    op.drop_index("ix_harvest_logs_level", table_name="harvest_logs")
    op.drop_index("ix_harvest_logs_harvest_job_id", table_name="harvest_logs")
    op.drop_table("harvest_logs")

    op.drop_index("ix_harvest_jobs_finished_at", table_name="harvest_jobs")
    op.drop_index("ix_harvest_jobs_started_at", table_name="harvest_jobs")
    op.drop_index("ix_harvest_jobs_status", table_name="harvest_jobs")
    op.drop_index("ix_harvest_jobs_connector_id", table_name="harvest_jobs")
    op.drop_table("harvest_jobs")

    op.drop_index("ix_connectors_enabled", table_name="connectors")
    op.drop_index("ix_connectors_repository_id", table_name="connectors")
    op.drop_index("ix_connectors_university_id", table_name="connectors")
    op.drop_index("ix_connectors_connector_type", table_name="connectors")
    op.drop_index("ix_connectors_code", table_name="connectors")
    op.drop_table("connectors")

    op.drop_index("ix_citations_observed_at", table_name="citations")
    op.drop_index("ix_citations_citing_source", table_name="citations")
    op.drop_index("ix_citations_citing_doi", table_name="citations")
    op.drop_index("ix_citations_publication_id", table_name="citations")
    op.drop_table("citations")

    op.drop_index("ix_research_projects_status", table_name="research_projects")
    op.drop_index(
        "ix_research_projects_principal_investigator_author_id", table_name="research_projects"
    )
    op.drop_index("ix_research_projects_funder_id", table_name="research_projects")
    op.drop_index("ix_research_projects_title", table_name="research_projects")
    op.drop_index("ix_research_projects_university_id", table_name="research_projects")
    op.drop_table("research_projects")

    op.drop_index("ix_datasets_doi", table_name="datasets")
    op.drop_index("ix_datasets_publication_id", table_name="datasets")
    op.drop_table("datasets")

    op.drop_index("ix_publication_keywords_keyword_id", table_name="publication_keywords")
    op.drop_index("ix_publication_keywords_publication_id", table_name="publication_keywords")
    op.drop_table("publication_keywords")

    op.drop_index("ix_keywords_normalized_term", table_name="keywords")
    op.drop_index("ix_keywords_term", table_name="keywords")
    op.drop_table("keywords")

    op.drop_index("ix_publication_authors_orcid", table_name="publication_authors")
    op.drop_index("ix_publication_authors_author_id", table_name="publication_authors")
    op.drop_index("ix_publication_authors_publication_id", table_name="publication_authors")
    op.drop_table("publication_authors")

    op.execute("DROP TRIGGER IF EXISTS trg_publications_search_vector ON publications")
    op.execute("DROP FUNCTION IF EXISTS researchhub_publication_search_vector_update")
    op.drop_index("ix_publications_search_vector", table_name="publications")
    op.drop_index("ix_publications_quality_score", table_name="publications")
    op.drop_index("ix_publications_source_type_year", table_name="publications")
    for column in [
        "is_deleted",
        "harvested_at",
        "source_type",
        "source",
        "repository_identifier",
        "repository_id",
        "isbn",
        "issn",
        "doi",
        "language",
        "publication_year",
        "publisher",
        "journal_id",
        "external_id",
    ]:
        op.drop_index(f"ix_publications_{column}", table_name="publications")
    op.drop_table("publications")

    op.drop_index("ix_organizations_country", table_name="organizations")
    op.drop_index("ix_organizations_type", table_name="organizations")
    op.drop_index("ix_organizations_normalized_name", table_name="organizations")
    op.drop_index("ix_organizations_name", table_name="organizations")
    op.drop_table("organizations")

    op.drop_index("ix_authors_department_id", table_name="authors")
    op.drop_index("ix_authors_university_id", table_name="authors")
    op.drop_index("ix_authors_orcid", table_name="authors")
    op.drop_index("ix_authors_normalized_name", table_name="authors")
    op.drop_index("ix_authors_full_name", table_name="authors")
    op.drop_table("authors")

    op.drop_index("ix_journals_eissn", table_name="journals")
    op.drop_index("ix_journals_issn", table_name="journals")
    op.drop_index("ix_journals_normalized_name", table_name="journals")
    op.drop_index("ix_journals_name", table_name="journals")
    op.drop_index("ix_journals_university_id", table_name="journals")
    op.drop_table("journals")

    op.drop_index("ix_repositories_is_active", table_name="repositories")
    op.drop_index("ix_repositories_platform", table_name="repositories")
    op.drop_index("ix_repositories_university_id", table_name="repositories")
    op.drop_table("repositories")

    op.drop_index("ix_departments_name", table_name="departments")
    op.drop_index("ix_departments_faculty_id", table_name="departments")
    op.drop_index("ix_departments_university_id", table_name="departments")
    op.drop_table("departments")

    op.drop_index("ix_faculties_name", table_name="faculties")
    op.drop_index("ix_faculties_university_id", table_name="faculties")
    op.drop_table("faculties")

    op.drop_index("ix_universities_is_active", table_name="universities")
    op.drop_index("ix_universities_country", table_name="universities")
    op.drop_index("ix_universities_code", table_name="universities")
    op.drop_table("universities")
