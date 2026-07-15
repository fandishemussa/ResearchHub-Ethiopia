"""Connector contract used by every metadata source integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


class ConnectorError(RuntimeError):
    """Base exception for connector failures."""


class TransientConnectorError(ConnectorError):
    """Raised for retryable provider or network failures."""


@dataclass(slots=True)
class ConnectorConfig:
    """Runtime configuration for a connector instance."""

    code: str
    name: str
    base_url: str
    source_type: str
    metadata_prefix: str = "oai_dc"
    set_spec: str | None = None
    from_date: date | None = None
    until_date: date | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    max_retries: int = 4
    backoff_factor: float = 0.5
    max_backoff_seconds: float = 30.0
    rate_limit_per_second: float = 2.0
    pool_connections: int = 10
    pool_maxsize: int = 20
    user_agent: str = "ResearchHubEthiopia/0.1"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RawRecord:
    """Raw provider record plus envelope metadata required for recovery."""

    identifier: str
    datestamp: datetime | None
    deleted: bool
    metadata: dict[str, list[str]]
    header: dict[str, Any]
    set_specs: list[str] = field(default_factory=list)
    raw_xml: str | None = None
    source: str | None = None
    metadata_prefix: str | None = None


@dataclass(slots=True)
class NormalizedPublication:
    """Canonical publication model emitted by every connector."""

    external_id: str | None
    title: str
    abstract: str | None
    authors: list[str]
    affiliations: list[str]
    journal: str | None
    publisher: str | None
    publication_date: date | None
    publication_year: int | None
    keywords: list[str]
    subjects: list[str]
    language: str | None
    doi: str | None
    orcid: str | None
    issn: str | None
    isbn: str | None
    license: str | None
    article_url: str | None
    pdf_url: str | None
    repository: str | None
    repository_identifier: str | None
    source: str
    source_type: str
    harvested_at: datetime
    updated_at: datetime
    quality_score: float
    is_deleted: bool
    raw_record: dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary for API export."""

        return asdict(self)


PublicationMetadata = NormalizedPublication


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A connector validation issue with a stable field name."""

    field: str
    message: str
    severity: str = "warning"


@dataclass(slots=True)
class ValidationResult:
    """Validation result produced before export."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)


class MetadataConnector(ABC):
    """Abstract connector interface for collection, normalization, and export."""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config

    @abstractmethod
    async def identify(self) -> dict[str, Any]:
        """Return source identity and capability metadata."""

    @abstractmethod
    def collect(self, **kwargs: Any) -> AsyncIterator[RawRecord]:
        """Collect raw records from the provider."""

    @abstractmethod
    def normalize(self, raw_record: RawRecord) -> NormalizedPublication:
        """Normalize one raw provider record into the canonical publication model."""

    @abstractmethod
    def validate(self, publication: NormalizedPublication) -> ValidationResult:
        """Validate a normalized publication before persistence."""

    @abstractmethod
    def export(self, publications: Iterable[NormalizedPublication]) -> list[dict[str, Any]]:
        """Export normalized publications to a serializable payload."""
