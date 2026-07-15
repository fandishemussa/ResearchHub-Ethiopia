"""Pydantic DTOs for API requests and responses."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class APIModel(BaseModel):
    """Base schema with ORM compatibility enabled."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UniversityCreate(APIModel):
    """Payload for registering an Ethiopian university."""

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=255)
    country: str = "Ethiopia"
    city: str | None = None
    website_url: HttpUrl | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UniversityRead(UniversityCreate):
    """University response model."""

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )


class RepositoryCreate(APIModel):
    """Payload for a repository or journal platform endpoint."""

    university_id: UUID
    name: str
    platform: str
    base_url: HttpUrl
    oai_endpoint: HttpUrl | None = None
    metadata_formats: list[str] = Field(default_factory=lambda: ["oai_dc"])


class RepositoryRead(RepositoryCreate):
    """Repository response model."""

    id: UUID
    is_active: bool
    last_harvested_at: datetime | None = None


class RepositoryUpdate(APIModel):
    """Editable institutional repository catalogue fields."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    platform: str | None = Field(default=None, min_length=2, max_length=80)
    base_url: HttpUrl | None = None
    oai_endpoint: HttpUrl | None = None
    metadata_formats: list[str] | None = None
    is_active: bool | None = None


class AuthorRead(APIModel):
    """Author response model."""

    id: UUID
    full_name: str
    normalized_name: str | None = None
    orcid: str | None = None
    affiliation: str | None = None


class PublicationCreate(APIModel):
    """Normalized publication payload accepted from connectors and API clients."""

    external_id: str | None = None
    title: str
    abstract: str | None = None
    publication_date: date | None = None
    publication_year: int | None = None
    language: str | None = None
    doi: str | None = None
    issn: str | None = None
    isbn: str | None = None
    license: str | None = None
    article_url: HttpUrl | None = None
    pdf_url: HttpUrl | None = None
    publisher: str | None = None
    source: str
    source_type: str
    repository_id: UUID | None = None
    repository_identifier: str | None = None
    authors: list[str] = Field(default_factory=list)
    affiliations: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    raw_record: dict[str, Any] = Field(default_factory=dict)


class PublicationRead(PublicationCreate):
    """Publication response model."""

    id: UUID
    harvested_at: datetime | None = None
    updated_at: datetime
    quality_score: Decimal | None = None
    is_deleted: bool


class SearchQuery(APIModel):
    """Search filters for PostgreSQL full-text and faceted lookup."""

    q: str | None = None
    author: str | None = None
    keyword: str | None = None
    journal: str | None = None
    year: int | None = None
    language: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SemanticSearchResult(APIModel):
    """Public nearest-neighbor result without its raw vector."""

    id: UUID
    title: str
    abstract_preview: str | None = None
    publication_year: int | None = None
    source: str
    article_url: str | None = None
    similarity: float


class SemanticSearchResponse(APIModel):
    """Semantic search response envelope."""

    query: str
    model: str
    count: int
    results: list[SemanticSearchResult]


class SimilarPublicationResult(APIModel):
    """Explainable publication-to-publication similarity result."""

    id: UUID
    title: str
    abstract_preview: str | None = None
    publication_year: int | None = None
    source: str
    article_url: str | None = None
    similarity_score: float
    shared_keywords: list[str] = Field(default_factory=list)
    shared_topics: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)


class PublicationSimilarityResponse(APIModel):
    """Similarity response envelope without raw vectors."""

    publication_id: UUID
    model: str
    count: int
    results: list[SimilarPublicationResult]


class ChatSessionCreate(APIModel):
    university_id: UUID | None = None
    title: str | None = Field(default=None, max_length=255)


class ChatSessionRead(APIModel):
    id: UUID
    university_id: UUID | None = None
    title: str
    is_pinned: bool = False
    last_model_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    is_pinned: bool | None = None


class ChatCitation(APIModel):
    index: int
    publication_id: UUID | None = None
    document_id: UUID | None = None
    chunk_id: UUID | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    url: str | None = None
    university: str | None = None
    repository: str | None = None
    source: str | None = None
    source_type: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    excerpt: str | None = None
    similarity_score: float | None = Field(default=None, ge=0, le=1)
    document_url: str | None = None
    landing_url: str | None = None
    preview_url: str | None = None
    document_type: str | None = None


class ChatFilters(APIModel):
    repositories: list[str] = Field(default_factory=list, max_length=20)
    universities: list[UUID] = Field(default_factory=list, max_length=20)
    document_types: list[str] = Field(default_factory=list, max_length=20)
    languages: list[str] = Field(default_factory=list, max_length=20)
    year_from: int | None = Field(default=None, ge=1800, le=3000)
    year_to: int | None = Field(default=None, ge=1800, le=3000)
    minimum_similarity: float = Field(default=0.35, ge=0.1, le=0.9)


class ChatRetrievalConfiguration(APIModel):
    top_documents: int = Field(default=5, ge=2, le=10)
    top_chunks: int = Field(default=10, ge=3, le=30)
    hybrid_search: bool = True
    rerank: bool = True
    include_full_text: bool = True
    include_metadata: bool = True
    citation_strictness: Literal["high", "balanced"] = "high"
    answer_length: Literal["concise", "balanced", "detailed"] = "balanced"
    response_language: str = Field(default="English", min_length=2, max_length=40)


class ChatMessageRead(APIModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    citations: list[ChatCitation] = Field(default_factory=list)
    retrieved_publication_ids: list[UUID] = Field(default_factory=list)
    model_name: str | None = None
    latency_ms: int | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class ChatQuery(APIModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    university_id: UUID | None = None
    year_from: int | None = Field(default=None, ge=1800, le=3000)
    year_to: int | None = Field(default=None, ge=1800, le=3000)
    publication_ids: list[UUID] = Field(default_factory=list, max_length=20)
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    pinned_chunk_ids: list[UUID] = Field(default_factory=list, max_length=30)
    mode: Literal[
        "ask",
        "summarize",
        "compare",
        "methodology",
        "evidence",
        "literature_review",
        "citation",
        "explain",
    ] = "ask"
    filters: ChatFilters = Field(default_factory=ChatFilters)
    retrieval: ChatRetrievalConfiguration = Field(default_factory=ChatRetrievalConfiguration)
    model: str | None = Field(default=None, max_length=255)
    stream: bool = False


class ChatResponse(APIModel):
    session_id: UUID
    message_id: UUID
    answer: str
    citations: list[ChatCitation]
    retrieved_publications: list[UUID]
    confidence: float
    model: str
    latency_ms: int | None = None
    usage: dict[str, int]
    warnings: list[str]
    retrieved_document_count: int = 0
    retrieved_chunk_count: int = 0
    grounding_status: Literal["strong", "partial", "insufficient"] = "insufficient"
    model_name: str
    follow_up_questions: list[str] = Field(default_factory=list)


class ChatFeedbackCreate(APIModel):
    message_id: UUID
    rating: Literal["helpful", "not_helpful", "inaccurate", "missing_sources"]
    comment: str | None = Field(default=None, max_length=1000)


class ResearchDocumentRead(APIModel):
    id: UUID
    publication_id: UUID | None = None
    source: str
    title: str | None = None
    document_url: str | None = None
    landing_url: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    page_count: int | None = None
    extraction_status: str
    extraction_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    extracted_at: datetime | None = None
    chunk_count: int = 0
    character_count: int = 0
    embedded_chunk_count: int = 0
    embedding_model: str | None = None


class ResearchDocumentPage(APIModel):
    items: list[ResearchDocumentRead]
    total: int
    limit: int
    offset: int


class DocumentChunkRead(APIModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    section_title: str | None = None
    content: str
    character_count: int
    embedding_model: str | None = None
    embedded_at: datetime | None = None
    content_type: str | None = None


class DocumentChunkPage(APIModel):
    items: list[DocumentChunkRead]
    total: int
    limit: int
    offset: int


class SummaryRequest(APIModel):
    summary_type: Literal[
        "short",
        "detailed",
        "structured",
        "executive",
        "plain-language",
        "methods",
        "findings",
        "limitations",
        "policy",
    ] = "short"
    max_length: int = Field(default=900, ge=100, le=5000)
    language: str = Field(default="en", max_length=20)
    force_regenerate: bool = False


class SummaryRead(APIModel):
    id: UUID
    publication_id: UUID
    summary_type: str
    summary_text: str
    model_name: str
    model_version: str | None = None
    source_fields: list[str]
    confidence_score: Decimal | None = None
    is_verified: bool
    generated_at: datetime


class AIKeywordRead(APIModel):
    id: UUID
    publication_id: UUID
    keyword: str
    confidence_score: Decimal
    extraction_method: str
    model_name: str | None = None
    status: str
    generated_at: datetime


class CitationRead(APIModel):
    id: UUID
    publication_id: UUID
    citation_style: str
    citation_text: str
    metadata_version: str
    is_verified: bool
    generated_at: datetime


class TrendOverviewPoint(APIModel):
    year: int
    publication_count: int
    methodology: str


class DuplicateCandidateRead(APIModel):
    id: UUID
    publication_id: UUID
    candidate_publication_id: UUID
    title_similarity: Decimal
    abstract_similarity: Decimal
    author_similarity: Decimal
    year_similarity: Decimal
    doi_match: bool
    final_score: Decimal
    status: str
    detected_at: datetime
    reviewed_at: datetime | None = None


class ConnectorCreate(APIModel):
    """Connector registration payload."""

    code: str
    name: str
    connector_type: str
    base_url: HttpUrl | None = None
    university_id: UUID | None = None
    repository_id: UUID | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    schedule: str | None = None


class ConnectorRead(ConnectorCreate):
    """Connector response model."""

    id: UUID
    enabled: bool
    last_cursor: str | None = None
    last_harvested_at: datetime | None = None


class HarvestRequest(APIModel):
    """Request to start or preview a harvest."""

    connector_id: UUID
    since: date | None = None
    until: date | None = None
    metadata_prefix: str = "oai_dc"
    set_spec: str | None = None


class HarvestJobRead(APIModel):
    """Harvest job response model."""

    id: UUID
    connector_id: UUID
    status: str
    records_seen: int
    records_imported: int
    records_updated: int
    records_deleted: int
    error_count: int
    started_at: datetime | None = None
    finished_at: datetime | None = None


SourceType = Literal[
    "oai_pmh",
    "dspace_oai",
    "ojs_oai",
    "dspace_discovery",
    "crossref",
    "openalex",
    "datacite",
    "xml_import",
    "json_import",
    "csv_import",
    "custom_rest",
]


class SourceCreate(APIModel):
    university_id: UUID
    repository_id: UUID | None = None
    journal_id: UUID | None = None
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=4000)
    source_type: SourceType
    base_url: HttpUrl | None = None
    api_url: HttpUrl | None = None
    oai_endpoint: HttpUrl | None = None
    metadata_prefix: str = Field(
        default="oai_dc", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    set_spec: str | None = Field(default=None, max_length=255)
    supported_formats: list[str] = Field(default_factory=list)
    connection_config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    is_public: bool = True


class SourceUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    base_url: HttpUrl | None = None
    api_url: HttpUrl | None = None
    oai_endpoint: HttpUrl | None = None
    metadata_prefix: str | None = Field(
        default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    set_spec: str | None = Field(default=None, max_length=255)
    supported_formats: list[str] | None = None
    connection_config: dict[str, Any] | None = None
    is_active: bool | None = None
    is_public: bool | None = None


class SourceRead(APIModel):
    id: UUID
    university_id: UUID | None
    repository_id: UUID | None
    journal_id: UUID | None
    name: str
    slug: str = Field(validation_alias="code")
    description: str | None
    source_type: str = Field(validation_alias="connector_type")
    base_url: str | None
    api_url: str | None
    oai_endpoint: str | None
    metadata_prefix: str
    set_spec: str | None
    supported_formats: list[str]
    is_active: bool = Field(validation_alias="enabled")
    is_public: bool
    status: str
    last_health_check_at: datetime | None
    last_successful_harvest_at: datetime | None
    last_failed_harvest_at: datetime | None
    last_error: str | None
    consecutive_failure_count: int
    total_records_harvested: int
    total_active_records: int
    total_deleted_records: int
    created_at: datetime
    updated_at: datetime


class SourceConnectionTestRequest(SourceCreate):
    pass


class SourceConnectionTestResult(APIModel):
    success: bool
    response_time_ms: int
    repository_name: str | None = None
    protocol_version: str | None = None
    admin_emails: list[str] = Field(default_factory=list)
    earliest_datestamp: str | None = None
    deletion_policy: str | None = None
    supported_metadata_formats: list[str] = Field(default_factory=list)
    supported_sets: list[dict[str, str]] = Field(default_factory=list)
    sample_record_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SourceHarvestRequest(APIModel):
    mode: Literal["full", "incremental", "dry_run", "resume"] = "incremental"
    from_date: date | None = None
    until_date: date | None = None
    set_spec: str | None = Field(default=None, max_length=255)
    metadata_prefix: str | None = Field(default=None, max_length=80)
    maximum_records: int | None = Field(default=None, ge=1, le=1_000_000)
    dry_run: bool = False
    import_to_database: bool = True
    include_deleted_records: bool = True
    force: bool = False
    resume_from_checkpoint: bool = False


class HarvestJobDetail(APIModel):
    id: UUID
    connector_id: UUID
    job_type: str
    mode: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    duration_ms: int | None
    total_pages: int
    processed_pages: int
    total_records: int
    fetched_records: int
    created_records: int
    updated_records: int
    unchanged_records: int
    deleted_records: int
    duplicate_records: int
    skipped_records: int
    failed_records: int
    checkpoint: dict[str, Any]
    resumption_token: str | None
    dry_run: bool
    error_summary: dict[str, Any]
    result_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class HarvestEventRead(APIModel):
    id: UUID
    harvest_job_id: UUID
    level: str
    event_type: str = Field(validation_alias="event")
    message: str
    details: dict[str, Any] = Field(validation_alias="context")
    created_at: datetime


class HarvestFailureRead(APIModel):
    id: UUID
    harvest_job_id: UUID
    external_id: str | None
    record_index: int | None
    error_type: str
    error_message: str
    retryable: bool
    retry_count: int
    resolved: bool
    resolved_at: datetime | None
    created_at: datetime


class TokenResponse(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime


class RefreshRequest(APIModel):
    refresh_token: str = Field(min_length=32, max_length=1000)


class LogoutRequest(APIModel):
    refresh_token: str = Field(min_length=32, max_length=1000)


class UserRead(APIModel):
    id: UUID
    email: str
    username: str
    full_name: str
    is_active: bool
    is_verified: bool
    is_suspended: bool
    university_id: UUID | None
    faculty_id: UUID | None
    department_id: UUID | None
    last_login_at: datetime | None
    created_at: datetime


class RefreshSessionRead(APIModel):
    id: UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class PasswordChangeRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=1000)
    new_password: str = Field(min_length=12, max_length=1000)


class PasswordForgotRequest(APIModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetRequest(APIModel):
    token: str = Field(min_length=32, max_length=1000)
    new_password: str = Field(min_length=12, max_length=1000)


class EmailVerifyRequest(APIModel):
    token: str = Field(min_length=32, max_length=1000)


class QualityReportRead(APIModel):
    """Metadata quality report response model."""

    id: UUID
    publication_id: UUID
    score: Decimal
    completeness_score: Decimal
    validity_score: Decimal
    consistency_score: Decimal
    uniqueness_score: Decimal
    timeliness_score: Decimal
    accessibility_score: Decimal
    final_score: Decimal
    grade: str
    missing_fields: list[str]
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str]
    recommendations: list[str] = Field(default_factory=list)
    issue_types: list[str] = Field(default_factory=list)
    is_current: bool = True
    assessed_at: datetime
    ruleset_version: str
    generated_at: datetime
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "id": "64b48c19-3e54-4b71-81b8-6d37c7b56c76",
                "publication_id": "2324e84e-2849-4ab8-9251-4eb7bcb6d513",
                "score": "92.50",
                "completeness_score": "100.00",
                "validity_score": "90.00",
                "consistency_score": "100.00",
                "uniqueness_score": "100.00",
                "timeliness_score": "80.00",
                "accessibility_score": "80.00",
                "final_score": "92.50",
                "grade": "A",
                "missing_fields": [],
                "validation_errors": [],
                "warnings": ["missing_license: License metadata is missing."],
                "recommendations": [],
                "issue_types": ["missing_license"],
                "is_current": True,
                "assessed_at": "2026-07-11T12:00:00Z",
                "ruleset_version": "metadata-quality-v1",
                "generated_at": "2026-07-11T12:00:00Z",
                "metadata": {"source": "haramaya-eajhbs", "source_type": "oai-pmh"},
            }
        },
    )


class QualityReportPage(APIModel):
    """Paginated metadata quality reports."""

    items: list[QualityReportRead]
    total: int
    limit: int
    offset: int


class QualityIssueRead(APIModel):
    """Flattened quality issue response."""

    publication_id: UUID
    report_id: UUID
    grade: str
    final_score: Decimal
    issue_type: str
    category: str
    message: str
    assessed_at: datetime


class QualityIssuePage(APIModel):
    """Paginated quality issue response."""

    items: list[QualityIssueRead]
    total: int
    limit: int
    offset: int


class QualitySummaryRead(APIModel):
    """Aggregate metadata quality summary."""

    total_reports: int
    assessed_publications: int
    active_publications: int
    deleted_publications: int
    average_final_score: Decimal
    grade_distribution: dict[str, int]
    dimension_averages: dict[str, Decimal]
    generated_at: datetime
    ruleset_version: str


class QualityRecalculateAllRead(APIModel):
    """Batch metadata quality recalculation response."""

    assessed_count: int
    created_count: int
    unchanged_count: int
    failed_count: int
