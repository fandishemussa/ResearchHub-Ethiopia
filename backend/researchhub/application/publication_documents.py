"""Centralized publication-to-document resolution and safe source probing."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.core.config import Settings, get_settings
from researchhub.infrastructure.persistence.models import Publication, ResearchDocument

UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
PDF_LINK_PATTERN = re.compile(
    r"(?:href|src)=[\"']([^\"']+(?:\.pdf|/bitstreams?/[^\"'#?]+/content)[^\"']*)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ResolvedPublicationDocument:
    publication_id: UUID
    research_document_id: UUID | None = None
    local_file_available: bool = False
    indexed: bool = False
    document_url: str | None = None
    landing_url: str | None = None
    source_kind: str = "none"
    resolution_status: str = "unavailable"
    document_status: str | None = None
    chunk_count: int = 0
    checksum_sha256: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DocumentSourceStatus:
    reachable: bool
    status_code: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    content_length: int | None = None
    is_pdf: bool = False
    requires_authentication: bool = False
    response_duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PublicationDocumentResolver:
    """Resolve and, when confident, repair the canonical document relationship."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, publication_id: UUID) -> ResolvedPublicationDocument:
        publication = await self.session.scalar(
            select(Publication).where(
                Publication.id == publication_id, Publication.is_deleted.is_(False)
            )
        )
        if publication is None:
            raise LookupError("Publication not found")

        document = await self.session.scalar(
            select(ResearchDocument)
            .where(ResearchDocument.publication_id == publication_id)
            .order_by(ResearchDocument.indexed_at.desc().nullslast())
        )
        source_kind = "publication_id"

        identifiers = {
            value.strip()
            for value in (publication.external_id, publication.repository_identifier)
            if value and value.strip()
        }
        if document is None and identifiers:
            document = await self.session.scalar(
                select(ResearchDocument)
                .where(ResearchDocument.external_id.in_(identifiers))
                .order_by(ResearchDocument.indexed_at.desc().nullslast())
            )
            source_kind = "external_id"

        if document is None:
            external_uuid = next(
                (
                    match.group(0).casefold()
                    for value in identifiers
                    if (match := UUID_PATTERN.search(value))
                ),
                None,
            )
            if external_uuid:
                document = await self.session.scalar(
                    select(ResearchDocument)
                    .where(
                        or_(
                            func.lower(ResearchDocument.local_path).contains(external_uuid),
                            func.lower(ResearchDocument.filename).contains(external_uuid),
                        )
                    )
                    .order_by(ResearchDocument.indexed_at.desc().nullslast())
                )
                source_kind = "filename_identifier"

        if document is None and publication.normalized_title:
            document = await self.session.scalar(
                select(ResearchDocument)
                .where(
                    func.lower(func.trim(ResearchDocument.title))
                    == publication.normalized_title.casefold().strip()
                )
                .order_by(ResearchDocument.indexed_at.desc().nullslast())
            )
            source_kind = "normalized_title"

        warnings: list[str] = []
        if document is not None:
            if document.publication_id is None:
                document.publication_id = publication_id
                await self.session.commit()
            local_available = bool(document.local_path and Path(document.local_path).is_file())
            indexed = document.extraction_status == "indexed" and document.chunk_count > 0
            if document.extraction_status == "indexed" and not indexed:
                warnings.append("The document is marked indexed but has no chunks.")
            return ResolvedPublicationDocument(
                publication_id=publication_id,
                research_document_id=document.id,
                local_file_available=local_available,
                indexed=indexed,
                document_url=document.document_url or publication.pdf_url,
                landing_url=document.landing_url or publication.article_url,
                source_kind=source_kind,
                resolution_status="indexed" if indexed else "registered",
                document_status=document.extraction_status,
                chunk_count=document.chunk_count,
                checksum_sha256=document.checksum_sha256,
                warnings=warnings,
            )

        document_url = publication.pdf_url
        landing_url = publication.article_url
        for candidate in publication.source_urls or []:
            if not isinstance(candidate, str) or not candidate.startswith(("http://", "https://")):
                continue
            if candidate.casefold().endswith(".pdf") or "/bitstream" in candidate.casefold():
                document_url = document_url or candidate
            else:
                landing_url = landing_url or candidate
        return ResolvedPublicationDocument(
            publication_id=publication_id,
            document_url=document_url,
            landing_url=landing_url,
            source_kind="publication_metadata" if document_url or landing_url else "none",
            resolution_status="url_available" if document_url or landing_url else "unavailable",
        )

    async def prepare_for_indexing(
        self, resolved: ResolvedPublicationDocument
    ) -> tuple[str | None, ResolvedPublicationDocument]:
        """Queue bounded download/index work and return its stable task id."""

        from researchhub.application.worker import celery_app

        publication = await self.session.get(Publication, resolved.publication_id)
        if publication is None:
            raise LookupError("Publication not found")
        task_id = f"publication-document-{resolved.publication_id}"
        if resolved.research_document_id and not resolved.local_file_available:
            document = await self.session.get(ResearchDocument, resolved.research_document_id)
            if document and document.extraction_status in {
                "pending",
                "downloading",
                "downloaded",
                "extracting",
                "chunking",
                "embedding",
            }:
                return task_id, resolved
        if resolved.research_document_id and resolved.local_file_available:
            document = await self.session.get(ResearchDocument, resolved.research_document_id)
            if document is None:
                return None, resolved
            document.extraction_status = "pending"
            document.last_attempted_at = datetime.now(UTC)
            await self.session.commit()
            celery_app.send_task(
                "researchhub.documents.index_file",
                kwargs={
                    "file_path": document.local_path,
                    "source": document.source,
                    "publication_id": str(publication.id),
                    "title": publication.title,
                    "external_id": publication.external_id,
                    "document_url": document.document_url,
                    "landing_url": document.landing_url,
                },
                task_id=task_id,
            )
            resolved.document_status = "pending"
            return task_id, resolved

        probe = DocumentSourceProbe()
        status = await probe.probe(resolved.document_url) if resolved.document_url else None
        if (status is None or not status.is_pdf) and resolved.landing_url:
            status = await probe.resolve_pdf_from_landing_page(resolved.landing_url)
        if status is None or not status.reachable or not status.is_pdf or not status.final_url:
            if status and status.error_message:
                resolved.warnings.append(status.error_message)
            return None, resolved

        settings = get_settings()
        storage = Path(settings.document_storage_path)
        local_path = storage / publication.source / f"{publication.id}.pdf"
        document = (
            await self.session.get(ResearchDocument, resolved.research_document_id)
            if resolved.research_document_id
            else None
        )
        if document is None:
            document = ResearchDocument(
                publication_id=publication.id,
                source=publication.source,
                external_id=publication.external_id,
                title=publication.title,
                local_path=str(local_path),
                filename=local_path.name,
                mime_type="application/pdf",
                file_extension=".pdf",
                metadata_json={"resolved_by": "publication_document_resolver"},
            )
            self.session.add(document)
        document.document_url = status.final_url
        document.landing_url = resolved.landing_url
        document.extraction_status = "pending"
        document.last_attempted_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(document)
        celery_app.send_task(
            "researchhub.documents.download_publication",
            kwargs={
                "document_id": str(document.id),
                "publication_id": str(publication.id),
            },
            task_id=task_id,
        )
        resolved.research_document_id = document.id
        resolved.document_status = "pending"
        resolved.document_url = status.final_url
        resolved.resolution_status = "registered"
        return task_id, resolved


class DocumentSourceProbe:
    """Bounded HTTP probe with SSRF protection and short-lived result caching."""

    _cache: dict[str, tuple[float, DocumentSourceStatus]] = {}

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("unsupported_protocol")
        if parsed.username or parsed.password:
            raise ValueError("credentials_in_url")
        hostname = parsed.hostname.casefold()
        if hostname in {item.casefold() for item in self.settings.document_probe_trusted_hosts}:
            return
        loop = asyncio.get_running_loop()
        addresses = await loop.run_in_executor(
            None, lambda: socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        )
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ValueError("private_network_target")

    async def probe(self, url: str) -> DocumentSourceStatus:
        now = time.monotonic()
        cached = self._cache.get(url)
        if cached and now - cached[0] < self.settings.document_probe_cache_ttl_seconds:
            return cached[1]
        started = time.monotonic()
        try:
            await self._validate_url(url)
        except (ValueError, OSError, socket.gaierror) as exc:
            result = DocumentSourceStatus(
                reachable=False,
                error_code=str(exc) or "invalid_url",
                error_message="The document address is not allowed or could not be resolved.",
            )
            self._cache[url] = (now, result)
            return result

        timeout = httpx.Timeout(
            connect=self.settings.http_connect_timeout_seconds,
            read=self.settings.http_read_timeout_seconds,
            write=self.settings.http_read_timeout_seconds,
            pool=self.settings.http_connect_timeout_seconds,
        )
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                max_redirects=self.settings.document_probe_redirect_limit,
                headers={"User-Agent": "ResearchHub-Ethiopia/1.0", "Accept-Encoding": "identity"},
            ) as client, client.stream("GET", url, headers={"Range": "bytes=0-4095"}) as response:
                await self._validate_url(str(response.url))
                content_length = int(response.headers.get("content-length", 0)) or None
                max_bytes = self.settings.document_download_max_size_mb * 1024 * 1024
                if content_length and content_length > max_bytes:
                    return DocumentSourceStatus(
                        reachable=True,
                        status_code=response.status_code,
                        final_url=str(response.url),
                        content_type=response.headers.get("content-type"),
                        content_length=content_length,
                        error_code="document_too_large",
                        error_message="The document exceeds the configured download limit.",
                    )
                prefix = b""
                async for block in response.aiter_bytes():
                    prefix += block
                    if len(prefix) >= 4096:
                        break
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                result = DocumentSourceStatus(
                    reachable=response.is_success,
                    status_code=response.status_code,
                    final_url=str(response.url),
                    content_type=content_type or None,
                    content_length=content_length,
                    is_pdf=prefix.startswith(b"%PDF-"),
                    requires_authentication=response.status_code in {401, 403},
                    response_duration_ms=round((time.monotonic() - started) * 1000),
                    error_code=None if response.is_success else "http_error",
                    error_message=None
                    if response.is_success
                    else "The document source rejected the request.",
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TooManyRedirects) as exc:
            result = DocumentSourceStatus(
                reachable=False,
                response_duration_ms=round((time.monotonic() - started) * 1000),
                error_code=type(exc).__name__.casefold(),
                error_message="The document source could not be reached safely.",
            )
        self._cache[url] = (now, result)
        return result

    async def resolve_pdf_from_landing_page(self, url: str) -> DocumentSourceStatus:
        landing = await self.probe(url)
        if not landing.reachable or landing.is_pdf:
            return landing
        timeout = httpx.Timeout(
            connect=self.settings.http_connect_timeout_seconds,
            read=self.settings.http_read_timeout_seconds,
            write=self.settings.http_read_timeout_seconds,
            pool=self.settings.http_connect_timeout_seconds,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                async with client.stream(
                    "GET", url, headers={"Range": "bytes=0-262143"}
                ) as response:
                    content = b""
                    async for block in response.aiter_bytes():
                        content += block
                        if len(content) >= 262144:
                            break
                    html = content.decode(response.encoding or "utf-8", errors="replace")
                    response_url = str(response.url)
                for match in PDF_LINK_PATTERN.finditer(html):
                    candidate = urljoin(response_url, match.group(1))
                    if urlparse(candidate).hostname != urlparse(response_url).hostname:
                        continue
                    probed = await self.probe(candidate)
                    if probed.reachable and probed.is_pdf:
                        return probed
        except httpx.HTTPError:
            pass
        return DocumentSourceStatus(
            reachable=True,
            status_code=landing.status_code,
            final_url=landing.final_url,
            content_type=landing.content_type,
            is_pdf=False,
            error_code="pdf_link_not_found",
            error_message="The repository page is reachable, but no validated PDF link was found.",
        )
