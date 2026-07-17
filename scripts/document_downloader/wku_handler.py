from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from .html_discovery import discover_from_landing_page
from .http_client import ResilientHttpClient
from .models import DocumentCandidate, Publication, SourceConfig
from .oai import iter_oai_publications
from .utils import unique

LOGGER = logging.getLogger(__name__)


SUPPORTED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
}

SUPPORTED_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


def _api_base(source: SourceConfig) -> str:
    return f"{source.base_url.rstrip('/')}/server/api"


def _discover_endpoint(
    source: SourceConfig,
) -> str:
    return f"{_api_base(source)}/discover/search/objects"


def _normalize_content_type(
    value: str | None,
) -> str:
    if not value:
        return ""

    return value.split(";", 1)[0].strip().lower()


def _metadata_values(
    item: dict[str, Any],
    key: str,
) -> list[str]:
    metadata = item.get(
        "metadata",
        {},
    )

    if not isinstance(metadata, dict):
        return []

    entries = metadata.get(
        key,
        [],
    )

    if not isinstance(entries, list):
        return []

    values: list[str] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        value = str(entry.get("value") or "").strip()

        if value:
            values.append(value)

    return unique(values)


def _first_metadata_value(
    item: dict[str, Any],
    key: str,
) -> str | None:
    values = _metadata_values(
        item,
        key,
    )

    return values[0] if values else None


def _extract_search_result(
    payload: dict[str, Any],
) -> dict[str, Any]:
    embedded = payload.get(
        "_embedded",
        {},
    )

    if not isinstance(embedded, dict):
        return {}

    search_result = embedded.get(
        "searchResult",
        {},
    )

    return search_result if isinstance(search_result, dict) else {}


def _extract_search_items(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    search_result = _extract_search_result(payload)

    embedded = search_result.get(
        "_embedded",
        {},
    )

    if not isinstance(embedded, dict):
        return []

    wrappers = embedded.get(
        "objects",
        [],
    )

    if not isinstance(wrappers, list):
        return []

    items: list[dict[str, Any]] = []

    for wrapper in wrappers:
        if not isinstance(wrapper, dict):
            continue

        wrapper_embedded = wrapper.get(
            "_embedded",
            {},
        )

        if not isinstance(
            wrapper_embedded,
            dict,
        ):
            continue

        item = wrapper_embedded.get(
            "indexableObject",
            {},
        )

        if not isinstance(item, dict):
            continue

        if item.get("type") != "item":
            continue

        if item.get("withdrawn", False):
            continue

        if not item.get(
            "discoverable",
            True,
        ):
            continue

        if not item.get(
            "inArchive",
            True,
        ):
            continue

        items.append(item)

    return items


def _extract_embedded_list(
    payload: dict[str, Any],
    key: str,
) -> list[dict[str, Any]]:
    embedded = payload.get(
        "_embedded",
        {},
    )

    if not isinstance(embedded, dict):
        return []

    values = embedded.get(
        key,
        [],
    )

    if not isinstance(values, list):
        return []

    return [value for value in values if isinstance(value, dict)]


def _normalize_handle(
    handle: str | None,
) -> str | None:
    if not handle:
        return None

    cleaned = handle.strip()

    if not cleaned:
        return None

    for prefix in (
        "http://hdl.handle.net/",
        "https://hdl.handle.net/",
    ):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :].strip("/")

    parsed = urlparse(cleaned)

    if "/handle/" in parsed.path:
        return parsed.path.split("/handle/", 1)[1].strip("/")

    if "/" in cleaned:
        return cleaned.strip("/")

    return None


def _select_item_handle(
    item: dict[str, Any],
) -> str | None:
    api_handle = _normalize_handle(str(item.get("handle") or ""))

    if api_handle:
        return api_handle

    identifier_values = _metadata_values(
        item,
        "dc.identifier.uri",
    )

    for identifier in identifier_values:
        handle = _normalize_handle(identifier)

        if handle:
            return handle

    return None


def _landing_url(
    source: SourceConfig,
    item: dict[str, Any],
) -> str | None:
    handle = _select_item_handle(item)

    if handle:
        return f"{source.base_url.rstrip('/')}/handle/{handle}"

    uuid = str(item.get("uuid") or item.get("id") or "").strip()

    if uuid:
        return f"{source.base_url.rstrip('/')}/items/{uuid}"

    return None


def _publication_from_item(
    source: SourceConfig,
    item: dict[str, Any],
) -> Publication | None:
    uuid = str(item.get("uuid") or item.get("id") or "").strip()

    if not uuid:
        return None

    handle = _select_item_handle(item)

    title = (
        _first_metadata_value(
            item,
            "dc.title",
        )
        or str(item.get("name") or "").strip()
        or None
    )

    authors = _metadata_values(
        item,
        "dc.contributor.author",
    )

    issued_date = _first_metadata_value(
        item,
        "dc.date.issued",
    )

    identifiers = _metadata_values(
        item,
        "dc.identifier.uri",
    )

    landing_url = _landing_url(
        source,
        item,
    )

    if landing_url:
        identifiers.append(landing_url)

    external_id = f"wku:{handle}" if handle else f"wku:{uuid}"

    return Publication(
        source=source.key,
        external_id=external_id,
        title=title,
        landing_url=landing_url,
        item_uuid=uuid,
        identifiers=unique(identifiers),
        authors=authors,
        issued_date=issued_date,
        raw=item,
    )


def iter_wku_rest_publications(
    client: ResilientHttpClient,
    source: SourceConfig,
    *,
    max_records: int | None = None,
    page_size: int = 100,
) -> Iterator[Publication]:
    """
    Enumerate WKU records through the DSpace 8 Discover API.
    """
    page = 0
    yielded = 0

    while True:
        payload = client.get_json(
            _discover_endpoint(source),
            params={
                "query": "*",
                "page": page,
                "size": page_size,
            },
            headers={
                "Accept": ("application/hal+json,application/json"),
            },
        )

        items = _extract_search_items(payload)

        if not items:
            return

        for item in items:
            publication = _publication_from_item(
                source,
                item,
            )

            if publication is None:
                continue

            yield publication

            yielded += 1

            if max_records is not None and yielded >= max_records:
                return

        search_result = _extract_search_result(payload)

        page_info = search_result.get(
            "page",
            {},
        )

        if not isinstance(page_info, dict):
            page_info = {}

        total_pages = page_info.get("totalPages")

        current_page = page_info.get(
            "number",
            page,
        )

        if isinstance(total_pages, int):
            if current_page + 1 >= total_pages:
                return

        else:
            links = search_result.get(
                "_links",
                {},
            )

            if not isinstance(links, dict):
                return

            next_link = links.get("next")

            if not next_link:
                return

        page += 1


def iter_wku_oai_publications(
    client: ResilientHttpClient,
    source: SourceConfig,
    *,
    max_records: int | None = None,
    from_date: str | None = None,
    set_spec: str | None = None,
) -> Iterator[Publication]:
    """
    OAI-PMH fallback for WKU.
    """
    oai_source = SourceConfig(
        key=source.key,
        name=source.name,
        kind="wku_oai",
        base_url=source.base_url,
        endpoint=(f"{source.base_url.rstrip('/')}/server/oai/request"),
        metadata_prefix="oai_dc",
    )

    for publication in iter_oai_publications(
        client,
        oai_source,
        max_records=max_records,
        from_date=from_date,
        set_spec=set_spec,
    ):
        normalized_identifiers: list[str] = []

        for identifier in publication.identifiers:
            handle = _normalize_handle(identifier)

            if handle:
                normalized_identifiers.append(f"{source.base_url.rstrip('/')}/handle/{handle}")
            else:
                normalized_identifiers.append(identifier)

        publication.identifiers = unique(normalized_identifiers)

        yield publication


def iter_wku_publications(
    client: ResilientHttpClient,
    source: SourceConfig,
    *,
    max_records: int | None = None,
    from_date: str | None = None,
    set_spec: str | None = None,
    page_size: int = 100,
) -> Iterator[Publication]:
    """
    Primary: DSpace REST API.
    Fallback: OAI-PMH.
    """
    yielded = 0

    try:
        for publication in iter_wku_rest_publications(
            client,
            source,
            max_records=max_records,
            page_size=page_size,
        ):
            yield publication
            yielded += 1

        return

    except Exception as exc:
        LOGGER.warning(
            "WKU REST enumeration failed: %s. Falling back to OAI-PMH.",
            exc,
        )

    remaining = None

    if max_records is not None:
        remaining = max(
            0,
            max_records - yielded,
        )

        if remaining == 0:
            return

    yield from iter_wku_oai_publications(
        client,
        source,
        max_records=remaining,
        from_date=from_date,
        set_spec=set_spec,
    )


def _bundle_bitstreams_url(
    source: SourceConfig,
    bundle: dict[str, Any],
) -> str | None:
    links = bundle.get(
        "_links",
        {},
    )

    if isinstance(links, dict):
        bitstreams_link = links.get(
            "bitstreams",
            {},
        )

        if isinstance(
            bitstreams_link,
            dict,
        ):
            href = bitstreams_link.get("href")

            if href:
                return str(href)

    bundle_uuid = str(bundle.get("uuid") or bundle.get("id") or "").strip()

    if not bundle_uuid:
        return None

    return f"{_api_base(source)}/core/bundles/{bundle_uuid}/bitstreams"


def _bitstream_content_url(
    source: SourceConfig,
    bitstream: dict[str, Any],
) -> str | None:
    links = bitstream.get(
        "_links",
        {},
    )

    if isinstance(links, dict):
        content_link = links.get(
            "content",
            {},
        )

        if isinstance(
            content_link,
            dict,
        ):
            href = content_link.get("href")

            if href:
                return str(href)

    uuid = str(bitstream.get("uuid") or bitstream.get("id") or "").strip()

    if not uuid:
        return None

    return f"{_api_base(source)}/core/bitstreams/{uuid}/content"


def _bitstream_filename(
    bitstream: dict[str, Any],
) -> str | None:
    name = str(bitstream.get("name") or "").strip()

    return name or None


def _bitstream_extension(
    bitstream: dict[str, Any],
) -> str:
    filename = _bitstream_filename(bitstream)

    if not filename:
        return ""

    decoded_name = unquote(filename)

    return PurePosixPath(decoded_name).suffix.lower()


def _metadata_mime_type(
    bitstream: dict[str, Any],
) -> str | None:
    metadata = bitstream.get(
        "metadata",
        {},
    )

    if not isinstance(metadata, dict):
        return None

    for key in (
        "dc.format.mimetype",
        "dc.format",
    ):
        values = metadata.get(
            key,
            [],
        )

        if not isinstance(values, list):
            continue

        for entry in values:
            if not isinstance(entry, dict):
                continue

            value = _normalize_content_type(str(entry.get("value") or ""))

            if value:
                return value

    return None


def _bitstream_mime_type(
    bitstream: dict[str, Any],
) -> str | None:
    mime_type = _metadata_mime_type(bitstream)

    if mime_type:
        return mime_type

    extension = _bitstream_extension(bitstream)

    if extension == ".pdf":
        return "application/pdf"

    if extension == ".doc":
        return "application/msword"

    if extension == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return None


def _is_supported_bitstream(
    bitstream: dict[str, Any],
) -> bool:
    extension = _bitstream_extension(bitstream)

    if extension in SUPPORTED_DOCUMENT_EXTENSIONS:
        return True

    mime_type = _bitstream_mime_type(bitstream)

    return mime_type in SUPPORTED_DOCUMENT_MIME_TYPES


def _is_original_bundle(
    bundle: dict[str, Any],
) -> bool:
    name = str(bundle.get("name") or "").strip().upper()

    return name == "ORIGINAL"


def discover_wku_documents_by_uuid(
    client: ResilientHttpClient,
    source: SourceConfig,
    item_uuid: str,
) -> list[DocumentCandidate]:
    """
    Discover documents through:

    item UUID
    -> ORIGINAL bundle
    -> bitstreams
    -> content endpoint
    """
    bundles_url = f"{_api_base(source)}/core/items/{item_uuid}/bundles"

    bundles_payload = client.get_json(
        bundles_url,
        params={
            "size": 100,
        },
        headers={
            "Accept": ("application/hal+json,application/json"),
        },
    )

    candidates: list[DocumentCandidate] = []
    seen_urls: set[str] = set()

    bundles = _extract_embedded_list(
        bundles_payload,
        "bundles",
    )

    for bundle in bundles:
        if not _is_original_bundle(bundle):
            continue

        bitstreams_url = _bundle_bitstreams_url(
            source,
            bundle,
        )

        if not bitstreams_url:
            continue

        bitstreams_payload = client.get_json(
            bitstreams_url,
            params={
                "size": 100,
            },
            headers={
                "Accept": ("application/hal+json,application/json"),
            },
        )

        bitstreams = _extract_embedded_list(
            bitstreams_payload,
            "bitstreams",
        )

        for bitstream in bitstreams:
            if not _is_supported_bitstream(bitstream):
                continue

            content_url = _bitstream_content_url(
                source,
                bitstream,
            )

            if not content_url or content_url in seen_urls:
                continue

            seen_urls.add(content_url)

            size_bytes = bitstream.get("sizeBytes")

            if not isinstance(
                size_bytes,
                int,
            ):
                size_bytes = None

            candidates.append(
                DocumentCandidate(
                    url=content_url,
                    filename=(_bitstream_filename(bitstream)),
                    mime_type=(_bitstream_mime_type(bitstream)),
                    size_bytes=size_bytes,
                )
            )

    return candidates


def _extract_publication_handle(
    publication: Publication,
) -> str | None:
    candidates = [
        publication.landing_url or "",
        *publication.identifiers,
        publication.external_id,
    ]

    for value in candidates:
        handle = _normalize_handle(value)

        if handle:
            return handle

    return None


def _resolve_uuid_by_handle(
    client: ResilientHttpClient,
    source: SourceConfig,
    handle: str,
) -> str | None:
    payload = client.get_json(
        f"{_api_base(source)}/pid/find",
        params={
            "id": handle,
        },
        headers={
            "Accept": ("application/hal+json,application/json"),
        },
    )

    uuid = payload.get("uuid") or payload.get("id")

    if uuid:
        return str(uuid)

    embedded = payload.get(
        "_embedded",
        {},
    )

    if isinstance(embedded, dict):
        for key in (
            "item",
            "indexableObject",
            "dspaceObject",
        ):
            item = embedded.get(key)

            if not isinstance(item, dict):
                continue

            uuid = item.get("uuid") or item.get("id")

            if uuid:
                return str(uuid)

    return None


def _resolve_publication_uuid(
    client: ResilientHttpClient,
    source: SourceConfig,
    publication: Publication,
) -> str | None:
    if publication.item_uuid:
        return publication.item_uuid

    handle = _extract_publication_handle(publication)

    if not handle:
        return None

    try:
        uuid = _resolve_uuid_by_handle(
            client,
            source,
            handle,
        )

        if uuid:
            publication.item_uuid = uuid

        return uuid

    except Exception as exc:
        LOGGER.warning(
            "WKU PID lookup failed for %s: %s",
            handle,
            exc,
        )
        return None


def discover_wku_documents(
    client: ResilientHttpClient,
    source: SourceConfig,
    publication: Publication,
) -> list[DocumentCandidate]:
    """
    Document discovery order:

    1. DSpace REST API
    2. HTML handle page
    """
    item_uuid = _resolve_publication_uuid(
        client,
        source,
        publication,
    )

    if item_uuid:
        try:
            candidates = discover_wku_documents_by_uuid(
                client,
                source,
                item_uuid,
            )

            if candidates:
                return candidates

        except Exception as exc:
            LOGGER.warning(
                "WKU REST document discovery failed for %s: %s",
                publication.external_id,
                exc,
            )

    landing_url = publication.landing_url

    if not landing_url:
        handle = _extract_publication_handle(publication)

        if handle:
            landing_url = f"{source.base_url.rstrip('/')}/handle/{handle}"

            publication.landing_url = landing_url

    if not landing_url:
        return []

    try:
        return discover_from_landing_page(
            client,
            source,
            landing_url,
        )

    except Exception as exc:
        LOGGER.warning(
            "WKU HTML fallback failed for %s: %s",
            publication.external_id,
            exc,
        )

        return []
