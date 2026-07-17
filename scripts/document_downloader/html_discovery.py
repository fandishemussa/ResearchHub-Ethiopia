from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from .http_client import ResilientHttpClient
from .models import DocumentCandidate, SourceConfig
from .utils import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    SUPPORTED_DOCUMENT_MIME_TYPES,
    normalize_content_type,
    unique,
    url_filename,
)

DOCUMENT_URL_HINTS = ("/bitstream/", "/content", "/download")


def _document_extension_from_url(url: str) -> str:
    parsed = urlparse(url)
    filename = unquote(PurePosixPath(parsed.path).name)
    return PurePosixPath(filename).suffix.lower()


def _is_supported_document_url(url: str) -> bool:
    return _document_extension_from_url(url) in SUPPORTED_DOCUMENT_EXTENSIONS


def _is_supported_document_link(url: str, text: str = "") -> bool:
    lowered_url = url.lower()
    lowered_text = text.lower()
    if _is_supported_document_url(url):
        return True
    if any(hint in lowered_url for hint in DOCUMENT_URL_HINTS):
        return True
    return any(
        word in lowered_text
        for word in ("pdf", "doc", "docx", "download", "full text", "view document")
    )


def _candidate_mime_type(url: str) -> str | None:
    extension = _document_extension_from_url(url)
    return {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(extension)


def discover_from_landing_page(
    client: ResilientHttpClient,
    source: SourceConfig,
    landing_url: str,
) -> list[DocumentCandidate]:
    response = client.request(
        "GET",
        landing_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        },
    )
    final_url = response.url
    content_type = normalize_content_type(response.headers.get("Content-Type"))

    if content_type in SUPPORTED_DOCUMENT_MIME_TYPES:
        filename = url_filename(final_url)
        response.close()
        return [DocumentCandidate(url=final_url, filename=filename, mime_type=content_type)]

    body = response.content
    first_bytes = body[:8]
    direct_mime: str | None = None
    if first_bytes.startswith(b"%PDF-"):
        direct_mime = "application/pdf"
    elif first_bytes.startswith(b"PK\x03\x04"):
        direct_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif first_bytes.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        direct_mime = "application/msword"

    if direct_mime:
        filename = url_filename(final_url)
        response.close()
        return [DocumentCandidate(url=final_url, filename=filename, mime_type=direct_mime)]

    html = response.text
    response.close()
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        text = anchor.get_text(" ", strip=True)
        absolute = urljoin(final_url, href)
        if _is_supported_document_link(absolute, text):
            links.append(absolute)

    for tag in soup.find_all(["meta", "link"]):
        value = tag.get("content") or tag.get("href")
        if not value:
            continue
        absolute = urljoin(final_url, str(value))
        if _is_supported_document_link(absolute):
            links.append(absolute)

    candidates = [
        DocumentCandidate(url=url, filename=url_filename(url), mime_type=_candidate_mime_type(url))
        for url in unique(links)
    ]

    if not candidates and source.kind == "aau_dspace7":
        handle_match = re.search(r"(?:handle\.net/|/handle/)([^?#]+)", final_url)
        if handle_match:
            handle = handle_match.group(1).strip("/")
            pid_url = urljoin(source.base_url, "/server/api/pid/find")
            try:
                payload = client.get_json(pid_url, params={"id": handle})
                uuid = payload.get("uuid") or payload.get("id")
                if uuid:
                    from .dspace7 import discover_aau_documents

                    return discover_aau_documents(client, source, str(uuid))
            except Exception:
                pass
    return candidates
