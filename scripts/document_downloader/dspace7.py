from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin

from .http_client import ResilientHttpClient
from .models import DocumentCandidate, Publication, SourceConfig
from .utils import SUPPORTED_DOCUMENT_EXTENSIONS


def _metadata_values(item: dict[str, Any], key: str) -> list[str]:
    metadata = item.get("metadata", {})
    if not isinstance(metadata, dict):
        return []
    values = metadata.get(key, [])
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for entry in values:
        if isinstance(entry, dict):
            value = str(entry.get("value") or "").strip()
            if value:
                result.append(value)
    return result


def _extract_search_result(payload: dict[str, Any]) -> dict[str, Any]:
    embedded = payload.get("_embedded", {})
    result = embedded.get("searchResult", {}) if isinstance(embedded, dict) else {}
    return result if isinstance(result, dict) else {}


def _extract_search_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = _extract_search_result(payload)
    embedded = result.get("_embedded", {})
    wrappers = embedded.get("objects", []) if isinstance(embedded, dict) else []
    output: list[dict[str, Any]] = []
    if not isinstance(wrappers, list):
        return output
    for wrapper in wrappers:
        wrapper_embedded = wrapper.get("_embedded", {}) if isinstance(wrapper, dict) else {}
        item = (
            wrapper_embedded.get("indexableObject", {})
            if isinstance(wrapper_embedded, dict)
            else {}
        )
        if not isinstance(item, dict):
            continue
        if item.get("type") != "item" or item.get("withdrawn"):
            continue
        if not item.get("discoverable", True) or not item.get("inArchive", True):
            continue
        output.append(item)
    return output


def iter_aau_publications(
    client: ResilientHttpClient,
    source: SourceConfig,
    *,
    max_records: int | None = None,
    page_size: int = 100,
) -> Iterator[Publication]:
    page = 0
    yielded = 0
    while True:
        payload = client.get_json(
            source.endpoint,
            params={"query": "*", "page": page, "size": page_size},
        )
        items = _extract_search_items(payload)
        if not items:
            return
        for item in items:
            uuid = str(item.get("uuid") or item.get("id") or "").strip()
            if not uuid:
                continue
            titles = _metadata_values(item, "dc.title")
            identifiers = _metadata_values(item, "dc.identifier.uri")
            handle = str(item.get("handle") or "").strip()
            landing_url = (
                identifiers[0]
                if identifiers
                else (
                    f"{source.base_url.rstrip('/')}/handle/{handle}"
                    if handle
                    else f"{source.base_url.rstrip('/')}/items/{uuid}"
                )
            )
            yield Publication(
                source=source.key,
                external_id=uuid,
                title=titles[0] if titles else str(item.get("name") or "").strip() or None,
                landing_url=landing_url,
                item_uuid=uuid,
                identifiers=identifiers,
                raw=item,
            )
            yielded += 1
            if max_records is not None and yielded >= max_records:
                return

        result = _extract_search_result(payload)
        page_info = result.get("page", {})
        total_pages = page_info.get("totalPages") if isinstance(page_info, dict) else None
        next_link = (
            result.get("_links", {}).get("next", {}).get("href")
            if isinstance(result.get("_links", {}), dict)
            else None
        )
        if isinstance(total_pages, int):
            if page + 1 >= total_pages:
                return
        elif not next_link:
            return
        page += 1


def _extract_embedded_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    embedded = payload.get("_embedded", {})
    values = embedded.get(key, []) if isinstance(embedded, dict) else []
    return (
        [value for value in values if isinstance(value, dict)] if isinstance(values, list) else []
    )


def _bitstream_document_info(bitstream: dict[str, Any]) -> tuple[str | None, str | None]:
    name = str(bitstream.get("name") or "").strip()
    extension = ""
    if "." in name:
        extension = "." + name.rsplit(".", 1)[-1].lower()

    metadata = bitstream.get("metadata", {})
    values: list[str] = []
    if isinstance(metadata, dict):
        for key in ("dc.format", "dc.format.mimetype"):
            entries = metadata.get(key, [])
            if isinstance(entries, list):
                values.extend(
                    str(entry.get("value") or "") for entry in entries if isinstance(entry, dict)
                )
    declared = " ".join(values).lower()

    if extension in SUPPORTED_DOCUMENT_EXTENSIONS:
        mime = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }[extension]
        return extension, mime
    if "application/pdf" in declared or "pdf" in declared:
        return ".pdf", "application/pdf"
    if "openxmlformats-officedocument.wordprocessingml.document" in declared or "docx" in declared:
        return ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if "application/msword" in declared or " ms word" in f" {declared}":
        return ".doc", "application/msword"
    return None, None


def discover_aau_documents(
    client: ResilientHttpClient,
    source: SourceConfig,
    item_uuid: str,
) -> list[DocumentCandidate]:
    bundles_url = urljoin(source.base_url, f"/server/api/core/items/{item_uuid}/bundles")
    bundles_payload = client.get_json(bundles_url, params={"size": 100})
    candidates: list[DocumentCandidate] = []

    for bundle in _extract_embedded_list(bundles_payload, "bundles"):
        if str(bundle.get("name") or "").strip().upper() != "ORIGINAL":
            continue
        links = bundle.get("_links", {})
        bitstreams_href = (
            links.get("bitstreams", {}).get("href") if isinstance(links, dict) else None
        )
        bundle_uuid = str(bundle.get("uuid") or bundle.get("id") or "").strip()
        if not bitstreams_href and bundle_uuid:
            bitstreams_href = urljoin(
                source.base_url, f"/server/api/core/bundles/{bundle_uuid}/bitstreams"
            )
        if not bitstreams_href:
            continue

        bitstreams_payload = client.get_json(str(bitstreams_href), params={"size": 100})
        for bitstream in _extract_embedded_list(bitstreams_payload, "bitstreams"):
            extension, mime_type = _bitstream_document_info(bitstream)
            if not extension:
                continue
            name = str(bitstream.get("name") or "").strip() or None
            links = bitstream.get("_links", {})
            content_href = links.get("content", {}).get("href") if isinstance(links, dict) else None
            bitstream_uuid = str(bitstream.get("uuid") or bitstream.get("id") or "").strip()
            if not content_href and bitstream_uuid:
                content_href = urljoin(
                    source.base_url, f"/server/api/core/bitstreams/{bitstream_uuid}/content"
                )
            if content_href:
                size = bitstream.get("sizeBytes")
                candidates.append(
                    DocumentCandidate(
                        url=str(content_href),
                        filename=name,
                        mime_type=mime_type,
                        size_bytes=size if isinstance(size, int) else None,
                    )
                )
    return candidates


# Backward-compatible aliases.
iter_dspace7_publications = iter_aau_publications
discover_dspace7_pdfs = discover_aau_documents
discover_aau_pdfs = discover_aau_documents
