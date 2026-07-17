from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceConfig:
    key: str
    name: str
    kind: str
    base_url: str
    endpoint: str
    metadata_prefix: str | None = None


@dataclass(slots=True)
class Publication:
    source: str
    external_id: str
    title: str | None = None
    landing_url: str | None = None
    item_uuid: str | None = None
    identifiers: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    issued_date: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentCandidate:
    """Backward-compatible candidate model for PDF, DOC, and DOCX files."""

    url: str
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None


@dataclass(slots=True)
class DownloadResult:
    source: str
    external_id: str
    title: str | None
    landing_url: str | None
    document_url: str | None
    local_path: str | None
    status: str
    document_type: str | None = None
    mime_type: str | None = None
    size_bytes: int = 0
    checksum_sha256: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Keep compatibility with older manifests.
        data["pdf_url"] = self.document_url if self.document_type == "pdf" else None
        return data
