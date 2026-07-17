"""Normalized SQLAlchemy 2.x models for the ResearchHub metadata graph."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from researchhub.infrastructure.persistence.base import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    """Return a typed UUID primary key column."""

    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Timestamp columns used on operational tables."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class University(Base, TimestampMixin):
    """University or national research institution."""

    __tablename__ = "universities"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    country: Mapped[str] = mapped_column(String(80), default="Ethiopia", index=True)
    city: Mapped[str | None] = mapped_column(String(120))
    website_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    faculties: Mapped[list[Faculty]] = relationship(back_populates="university")
    departments: Mapped[list[Department]] = relationship(back_populates="university")
    repositories: Mapped[list[Repository]] = relationship(back_populates="university")


class Faculty(Base, TimestampMixin):
    """Faculty, college, or school within a university."""

    __tablename__ = "faculties"
    __table_args__ = (UniqueConstraint("university_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    university_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("universities.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    code: Mapped[str | None] = mapped_column(String(60))

    university: Mapped[University] = relationship(back_populates="faculties")
    departments: Mapped[list[Department]] = relationship(back_populates="faculty")


class Department(Base, TimestampMixin):
    """Academic department attached to a faculty and university."""

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("university_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    university_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("universities.id"), index=True)
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("faculties.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    code: Mapped[str | None] = mapped_column(String(60))

    university: Mapped[University] = relationship(back_populates="departments")
    faculty: Mapped[Faculty | None] = relationship(back_populates="departments")


class Repository(Base, TimestampMixin):
    """Institutional repository, DSpace endpoint, OJS site, or related source."""

    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("university_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    university_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("universities.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(80), index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    oai_endpoint: Mapped[str | None] = mapped_column(String(500))
    metadata_formats: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_harvested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    university: Mapped[University] = relationship(back_populates="repositories")
    publications: Mapped[list[Publication]] = relationship(back_populates="repository")


class Journal(Base, TimestampMixin):
    """Journal metadata, including local university journals and external journals."""

    __tablename__ = "journals"

    id: Mapped[uuid.UUID] = uuid_pk()
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str | None] = mapped_column(String(255), index=True)
    issn: Mapped[str | None] = mapped_column(String(20), index=True)
    eissn: Mapped[str | None] = mapped_column(String(20), index=True)
    publisher: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(500))

    publications: Mapped[list[Publication]] = relationship(back_populates="journal")


class PublicationType(Base, TimestampMixin):
    """Controlled publication type vocabulary, such as article, thesis, or dataset."""

    __tablename__ = "publication_types"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    normalized_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    publications: Mapped[list[Publication]] = relationship(back_populates="publication_type")


class License(Base, TimestampMixin):
    """Controlled license vocabulary used by publications and datasets."""

    __tablename__ = "licenses"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(500))

    publications: Mapped[list[Publication]] = relationship(back_populates="license_record")


class Author(Base, TimestampMixin):
    """Person credited as an author or contributor."""

    __tablename__ = "authors"

    id: Mapped[uuid.UUID] = uuid_pk()
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str | None] = mapped_column(String(255), index=True)
    orcid: Mapped[str | None] = mapped_column(String(19), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    affiliation: Mapped[str | None] = mapped_column(String(500))
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id"), index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id"), index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    publications: Mapped[list[PublicationAuthor]] = relationship(back_populates="author")


class Organization(Base, TimestampMixin):
    """External organization such as funder, publisher, partner, or affiliation."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str | None] = mapped_column(String(255), index=True)
    organization_type: Mapped[str | None] = mapped_column("type", String(80), index=True)
    country: Mapped[str | None] = mapped_column(String(80), index=True)
    ror_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    url: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class Publication(Base, TimestampMixin):
    """Canonical normalized publication record shared by every connector."""

    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        Index("ix_publications_source_type_year", "source_type", "publication_year"),
        Index("ix_publications_quality_score", "quality_score"),
        Index("ix_publications_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    external_id: Mapped[str | None] = mapped_column(String(500), index=True)
    title: Mapped[str] = mapped_column(Text)
    normalized_title: Mapped[str | None] = mapped_column(String(1000), index=True)
    abstract: Mapped[str | None] = mapped_column(Text)
    affiliations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    journal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journals.id"), index=True)
    publication_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("publication_types.id"), index=True
    )
    license_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("licenses.id"), index=True)
    publisher: Mapped[str | None] = mapped_column(String(255), index=True)
    publication_date: Mapped[date | None] = mapped_column(Date)
    publication_year: Mapped[int | None] = mapped_column(Integer, index=True)
    subjects: Mapped[list[str]] = mapped_column(JSONB, default=list)
    language: Mapped[str | None] = mapped_column(String(20), index=True)
    doi: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    issn: Mapped[str | None] = mapped_column(String(20), index=True)
    isbn: Mapped[str | None] = mapped_column(String(32), index=True)
    license: Mapped[str | None] = mapped_column(String(255))
    article_url: Mapped[str | None] = mapped_column(String(1000))
    pdf_url: Mapped[str | None] = mapped_column(String(1000))
    source_urls: Mapped[list[str]] = mapped_column(JSONB, default=list)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id"), index=True
    )
    repository_identifier: Mapped[str | None] = mapped_column(String(500), index=True)
    repository_datestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    source: Mapped[str] = mapped_column(String(120), index=True)
    source_type: Mapped[str] = mapped_column(String(80), index=True)
    harvested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_record: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    normalized_record: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding_content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    embedding_failure_code: Mapped[str | None] = mapped_column(String(80), index=True)
    embedding_failure_message: Mapped[str | None] = mapped_column(Text)
    embedding_retry_count: Mapped[int] = mapped_column(Integer, default=0)

    journal: Mapped[Journal | None] = relationship(back_populates="publications")
    publication_type: Mapped[PublicationType | None] = relationship(back_populates="publications")
    license_record: Mapped[License | None] = relationship(back_populates="publications")
    repository: Mapped[Repository | None] = relationship(back_populates="publications")
    authors: Mapped[list[PublicationAuthor]] = relationship(back_populates="publication")
    keywords: Mapped[list[PublicationKeyword]] = relationship(back_populates="publication")
    datasets: Mapped[list[Dataset]] = relationship(back_populates="publication")
    quality_reports: Mapped[list[QualityReport]] = relationship(back_populates="publication")


class PublicationEmbeddingRecord(Base, TimestampMixin):
    """Versioned publication embedding with reproducible input provenance."""

    __tablename__ = "publication_embeddings"
    __table_args__ = (
        UniqueConstraint("publication_id", "model_name"),
        Index(
            "ix_publication_embeddings_vector_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(255), index=True)
    model_version: Mapped[str | None] = mapped_column(String(120))
    embedding_dimension: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    input_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)


class PublicationAuthor(Base, TimestampMixin):
    """Join table preserving author order and source affiliation strings."""

    __tablename__ = "publication_authors"
    __table_args__ = (UniqueConstraint("publication_id", "author_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("authors.id"), index=True)
    author_order: Mapped[int] = mapped_column(Integer, default=1)
    affiliation: Mapped[str | None] = mapped_column(String(500))
    orcid: Mapped[str | None] = mapped_column(String(19), index=True)

    publication: Mapped[Publication] = relationship(back_populates="authors")
    author: Mapped[Author] = relationship(back_populates="publications")


class Keyword(Base, TimestampMixin):
    """Normalized keyword or controlled vocabulary term."""

    __tablename__ = "keywords"

    id: Mapped[uuid.UUID] = uuid_pk()
    term: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    normalized_term: Mapped[str] = mapped_column(String(255), index=True)
    vocabulary: Mapped[str | None] = mapped_column(String(120))

    publications: Mapped[list[PublicationKeyword]] = relationship(back_populates="keyword")


class PublicationKeyword(Base, TimestampMixin):
    """Publication-keyword relationship with optional relevance scoring."""

    __tablename__ = "publication_keywords"
    __table_args__ = (UniqueConstraint("publication_id", "keyword_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    keyword_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("keywords.id"), index=True)
    relevance_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    publication: Mapped[Publication] = relationship(back_populates="keywords")
    keyword: Mapped[Keyword] = relationship(back_populates="publications")


class Dataset(Base, TimestampMixin):
    """Dataset associated with a publication or research project."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("publications.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    doi: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(1000))
    repository: Mapped[str | None] = mapped_column(String(255))
    license: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    publication: Mapped[Publication | None] = relationship(back_populates="datasets")


class ResearchProject(Base, TimestampMixin):
    """Institutional research project that may produce publications and datasets."""

    __tablename__ = "research_projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    funder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    principal_investigator_author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("authors.id"), index=True
    )
    status: Mapped[str | None] = mapped_column(String(80), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class Citation(Base, TimestampMixin):
    """Citation count or citing-work record from external citation providers."""

    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    citing_doi: Mapped[str | None] = mapped_column(String(255), index=True)
    citing_title: Mapped[str | None] = mapped_column(Text)
    citing_source: Mapped[str | None] = mapped_column(String(120), index=True)
    citation_count: Mapped[int] = mapped_column(Integer, default=0)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class Connector(Base, TimestampMixin):
    """Configurable metadata connector for a repository or external provider."""

    __tablename__ = "connectors"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    connector_type: Mapped[str] = mapped_column(String(80), index=True)
    base_url: Mapped[str | None] = mapped_column(String(500))
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id"), index=True
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repositories.id"), index=True
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    schedule: Mapped[str | None] = mapped_column(String(120))
    last_cursor: Mapped[str | None] = mapped_column(Text)
    last_harvested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    journal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("journals.id"), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    api_url: Mapped[str | None] = mapped_column(String(500))
    oai_endpoint: Mapped[str | None] = mapped_column(String(500), index=True)
    metadata_prefix: Mapped[str] = mapped_column(String(80), default="oai_dc")
    set_spec: Mapped[str | None] = mapped_column(String(255))
    supported_formats: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_harvest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failed_harvest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    total_records_harvested: Mapped[int] = mapped_column(Integer, default=0)
    total_active_records: Mapped[int] = mapped_column(Integer, default=0)
    total_deleted_records: Mapped[int] = mapped_column(Integer, default=0)


class HarvestJob(Base, TimestampMixin):
    """Execution record for one connector harvesting run."""

    __tablename__ = "harvest_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    connector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("connectors.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    since: Mapped[date | None] = mapped_column(Date)
    until: Mapped[date | None] = mapped_column(Date)
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_imported: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_deleted: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    cursor: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    job_type: Mapped[str] = mapped_column(String(40), default="online_harvest", index=True)
    mode: Mapped[str] = mapped_column(String(30), default="full", index=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    processed_pages: Mapped[int] = mapped_column(Integer, default=0)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    fetched_records: Mapped[int] = mapped_column(Integer, default=0)
    created_records: Mapped[int] = mapped_column(Integer, default=0)
    updated_records: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_records: Mapped[int] = mapped_column(Integer, default=0)
    deleted_records: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_records: Mapped[int] = mapped_column(Integer, default=0)
    skipped_records: Mapped[int] = mapped_column(Integer, default=0)
    failed_records: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    resumption_token: Mapped[str | None] = mapped_column(Text)
    input_filename: Mapped[str | None] = mapped_column(String(500))
    input_file_checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    error_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class HarvestLog(Base):
    """Structured event log for individual harvesting jobs."""

    __tablename__ = "harvest_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    harvest_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("harvest_jobs.id"), index=True)
    level: Mapped[str] = mapped_column(String(20), index=True)
    event: Mapped[str] = mapped_column(String(120), index=True)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class HarvestFailure(Base):
    """Record-level harvest or import failure with retry state."""

    __tablename__ = "harvest_failures"

    id: Mapped[uuid.UUID] = uuid_pk()
    harvest_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("harvest_jobs.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(500), index=True)
    record_index: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str] = mapped_column(String(120), index=True)
    error_message: Mapped[str] = mapped_column(Text)
    raw_record: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class ImportFile(Base):
    """Validated metadata upload stored under a generated server filename."""

    __tablename__ = "import_files"

    id: Mapped[uuid.UUID] = uuid_pk()
    harvest_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("harvest_jobs.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(500))
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)
    storage_path: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[str] = mapped_column(String(120))
    file_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    validation_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class MetadataHistory(Base):
    """Field-level metadata provenance and change history."""

    __tablename__ = "metadata_history"

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    source: Mapped[str] = mapped_column(String(120), index=True)
    field_name: Mapped[str] = mapped_column(String(120), index=True)
    old_value: Mapped[dict[str, Any] | list[Any] | str | int | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | list[Any] | str | int | None] = mapped_column(JSONB)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    changed_by: Mapped[str | None] = mapped_column(String(120))


class QualityReport(Base):
    """Metadata quality report generated during harvest or enrichment."""

    __tablename__ = "quality_reports"
    __table_args__ = (
        Index("ix_quality_reports_publication_current", "publication_id", "is_current"),
        Index("ix_quality_reports_grade_score", "grade", "final_score"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    completeness_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    validity_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    consistency_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    uniqueness_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    timeliness_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    accessibility_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    final_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), index=True)
    grade: Mapped[str] = mapped_column(String(1), default="F", index=True)
    missing_fields: Mapped[list[str]] = mapped_column(JSONB, default=list)
    validation_errors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    issue_types: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    ruleset_version: Mapped[str] = mapped_column(
        String(40), default="metadata-quality-v1", index=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    publication: Mapped[Publication] = relationship(back_populates="quality_reports")


class ChatSession(Base, TimestampMixin):
    """University-scoped research assistant conversation."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="New research conversation")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_model_name: Mapped[str | None] = mapped_column(String(255))

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    """A grounded user or assistant message with retrieval provenance."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    retrieved_publication_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    model_name: Mapped[str | None] = mapped_column(String(255))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class ChatFeedback(Base):
    """User feedback for a single assistant response."""

    __tablename__ = "chat_feedback"
    __table_args__ = (UniqueConstraint("message_id", "user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    rating: Mapped[str] = mapped_column(String(40), index=True)
    comment: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PublicationSummary(Base):
    """Cached, source-grounded generated publication summary."""

    __tablename__ = "publication_summaries"
    __table_args__ = (UniqueConstraint("publication_id", "summary_type", "content_hash"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    summary_type: Mapped[str] = mapped_column(String(50), index=True)
    summary_text: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(255))
    model_version: Mapped[str | None] = mapped_column(String(120))
    source_fields: Mapped[list[str]] = mapped_column(JSONB, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    language: Mapped[str] = mapped_column(String(20), default="en")
    source_type: Mapped[str] = mapped_column(String(30), default="metadata")
    model_provider: Mapped[str] = mapped_column(String(40), default="local")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_text: Mapped[str | None] = mapped_column(Text)
    research_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_documents.id", ondelete="SET NULL"), index=True
    )
    document_checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    pages_used: Mapped[list[int]] = mapped_column(JSONB, default=list)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_version: Mapped[str] = mapped_column(String(80), default="summary-v2")
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class PublicationKeywordAI(Base):
    """AI-extracted keyword distinct from harvested source keywords."""

    __tablename__ = "publication_keywords_ai"
    __table_args__ = (UniqueConstraint("publication_id", "keyword", "extraction_method"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(255), index=True)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    extraction_method: Mapped[str] = mapped_column(String(80), index=True)
    model_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PublicationCitationAI(Base):
    """Cached deterministic citation rendering."""

    __tablename__ = "publication_citations"
    __table_args__ = (UniqueConstraint("publication_id", "citation_style", "metadata_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    citation_style: Mapped[str] = mapped_column(String(40), index=True)
    citation_text: Mapped[str] = mapped_column(Text)
    metadata_version: Mapped[str] = mapped_column(String(64), index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DuplicateCandidate(Base):
    """Reviewable duplicate signal; records are never automatically deleted."""

    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        UniqueConstraint("publication_id", "candidate_publication_id"),
        Index("ix_duplicate_candidates_status_score", "status", "final_score"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    publication_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publications.id"), index=True)
    candidate_publication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publications.id"), index=True
    )
    title_similarity: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    abstract_similarity: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    author_similarity: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    year_similarity: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    doi_match: Mapped[bool] = mapped_column(Boolean, default=False)
    final_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), index=True)
    status: Mapped[str] = mapped_column(String(40), default="detected", index=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchTrend(Base):
    """Cached, explainable research trend result."""

    __tablename__ = "research_trends"
    __table_args__ = (
        Index(
            "ix_research_trends_scope_period",
            "scope_type",
            "scope_id",
            "period_start",
            "period_end",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    scope_type: Mapped[str] = mapped_column(String(40), index=True)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    trend_type: Mapped[str] = mapped_column(String(60), index=True)
    label: Mapped[str] = mapped_column(String(255), index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    publication_count: Mapped[int] = mapped_column(Integer, default=0)
    previous_period_count: Mapped[int] = mapped_column(Integer, default=0)
    growth_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    trend_score: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    methodology: Mapped[str] = mapped_column(Text)
    supporting_publication_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AIJob(Base, TimestampMixin):
    """Progress and error state for an idempotent AI background operation."""

    __tablename__ = "ai_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    job_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    provider: Mapped[str] = mapped_column(String(40), default="local")
    model_name: Mapped[str | None] = mapped_column(String(255))
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    progress_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    input_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIUsageLog(Base):
    """Non-secret operational usage and cost telemetry."""

    __tablename__ = "ai_usage_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    operation: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    model_name: Mapped[str] = mapped_column(String(255), index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error_type: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class User(Base, TimestampMixin):
    """Authenticated platform identity."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    university_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("universities.id"), index=True
    )
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("faculties.id"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id"), index=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    replaced_by_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_sessions.id")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchDocument(Base, TimestampMixin):
    __tablename__ = "research_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    publication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    local_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    document_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    landing_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    filename: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    file_extension: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    character_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )

    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    extraction_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    extraction_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    processing_error_code: Mapped[str | None] = mapped_column(String(80), index=True)
    technical_error: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    downloaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "research_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    page_start: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    page_end: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    section_title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(384),
        nullable=True,
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    embedded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document: Mapped[ResearchDocument] = relationship(
        back_populates="chunks",
    )
