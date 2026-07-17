from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterator
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlparse

from .http_client import ResilientHttpClient
from .models import DocumentCandidate, Publication, SourceConfig

LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
}

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


def rewrite_bdu_url(source: SourceConfig, value: str) -> str:
    """Rewrite a BDU handle resolver URL to the configured repository host.

    Legacy metadata commonly stores ``hdl.handle.net`` links.  Keeping the
    handle path while using the managed source host avoids an unnecessary
    external redirect and makes the result deterministic in downloads and
    tests. Non-handle URLs are returned unchanged.
    """

    handle = _handle_from_uri(value)
    if handle is None:
        return value
    return f"{_base_url(source)}/handle/{handle}"


def _base_url(source: SourceConfig) -> str:
    return source.base_url.rstrip("/")


def _rest_url(
    source: SourceConfig,
    path: str,
) -> str:
    return f"{_base_url(source)}/rest/{path.lstrip('/')}"


def _repository_handle_url(
    source: SourceConfig,
    handle: str | None,
) -> str | None:
    if not handle:
        return None

    cleaned = handle.strip()

    for prefix in (
        "http://hdl.handle.net/",
        "https://hdl.handle.net/",
    ):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break

    cleaned = cleaned.removeprefix("/handle/")
    cleaned = cleaned.removeprefix("handle/")

    if not cleaned:
        return None

    return f"{_base_url(source)}/handle/{cleaned}"


def _handle_from_uri(
    value: str | None,
) -> str | None:
    if not value:
        return None

    cleaned = value.strip()

    for prefix in (
        "http://hdl.handle.net/",
        "https://hdl.handle.net/",
    ):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :].strip("/")

    if "/handle/" in cleaned:
        return cleaned.split("/handle/", 1)[1].strip("/")

    if cleaned.startswith("123456789/"):
        return cleaned

    return None


def _get_json(
    client: ResilientHttpClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    return client.get_json_value(
        url,
        params=params,
        headers={
            "Accept": "application/json",
        },
    )


def _metadata_multimap(
    rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        key = str(row.get("key") or "").strip()
        value = str(row.get("value") or "").strip()

        if key and value:
            values[key].append(value)

    return dict(values)


def _first(
    metadata: dict[str, list[str]],
    *keys: str,
) -> str | None:
    for key in keys:
        values = metadata.get(key) or []

        for value in values:
            cleaned = str(value).strip()

            if cleaned:
                return cleaned

    return None


def _all_values(
    metadata: dict[str, list[str]],
    *keys: str,
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for key in keys:
        for value in metadata.get(key) or []:
            cleaned = str(value).strip()

            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)

    return result


def normalize_bdu_metadata(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata = _metadata_multimap(rows)

    handle_uri = _first(
        metadata,
        "dc.identifier.uri",
        "dc.identifier",
    )

    handle = _handle_from_uri(handle_uri)

    return {
        "title": _first(
            metadata,
            "dc.title",
        ),
        "authors": _all_values(
            metadata,
            "dc.contributor.author",
            "dc.creator",
        ),
        "abstract": _first(
            metadata,
            "dc.description.abstract",
            "dc.description",
        ),
        "subjects": _all_values(
            metadata,
            "dc.subject",
        ),
        "issued": _first(
            metadata,
            "dc.date.issued",
            "dc.date",
        ),
        "language": _first(
            metadata,
            "dc.language.iso",
            "dc.language",
        ),
        "document_type": _first(
            metadata,
            "dc.type",
        ),
        "publisher": _first(
            metadata,
            "dc.publisher",
        ),
        "handle": handle,
        "handle_uri": handle_uri,
        "accessioned_at": _first(
            metadata,
            "dc.date.accessioned",
        ),
        "available_at": _first(
            metadata,
            "dc.date.available",
        ),
        "raw_metadata": metadata,
    }


def _filename_from_bitstream(
    bitstream: dict[str, Any],
) -> str | None:
    for key in (
        "name",
        "filename",
        "fileName",
    ):
        value = bitstream.get(key)

        if value:
            return str(value).strip()

    return None


def _mime_from_bitstream(
    bitstream: dict[str, Any],
) -> str | None:
    for key in (
        "mimeType",
        "mime_type",
        "format",
        "contentType",
    ):
        value = bitstream.get(key)

        if value:
            return str(value).split(";", 1)[0].strip().lower()

    return None


def _extension_from_filename(
    filename: str | None,
) -> str | None:
    if not filename:
        return None

    suffix = PurePosixPath(filename).suffix.lower()

    return suffix if suffix else None


def _is_supported_bitstream(
    bitstream: dict[str, Any],
) -> bool:
    filename = _filename_from_bitstream(bitstream)
    extension = _extension_from_filename(filename)
    mime_type = _mime_from_bitstream(bitstream)

    if extension in SUPPORTED_EXTENSIONS:
        return True

    return mime_type in SUPPORTED_MIME_TYPES


def _bitstream_id(
    bitstream: dict[str, Any],
) -> str | None:
    value = bitstream.get("id")

    if value is None:
        value = bitstream.get("uuid")

    if value is None:
        return None

    return str(value).strip()


def _bitstream_download_url(
    source: SourceConfig,
    bitstream: dict[str, Any],
) -> str | None:
    base = _base_url(source)

    for key in (
        "retrieveLink",
        "retrieve",
        "downloadLink",
        "contentLink",
    ):
        value = bitstream.get(key)

        if value:
            return urljoin(
                f"{base}/",
                str(value),
            )

    link = bitstream.get("link")

    if link:
        link_value = str(link)

        if link_value.endswith("/retrieve"):
            return urljoin(
                f"{base}/",
                link_value,
            )

    bitstream_id = _bitstream_id(bitstream)

    if not bitstream_id:
        return None

    return _rest_url(
        source,
        f"bitstreams/{bitstream_id}/retrieve",
    )


def _bitstream_candidate(
    source: SourceConfig,
    bitstream: dict[str, Any],
) -> DocumentCandidate | None:
    if not _is_supported_bitstream(bitstream):
        return None

    url = _bitstream_download_url(
        source,
        bitstream,
    )

    if not url:
        return None

    filename = _filename_from_bitstream(bitstream)
    mime_type = _mime_from_bitstream(bitstream)

    if not mime_type:
        extension = _extension_from_filename(filename)

        if extension:
            mime_type = MIME_BY_EXTENSION.get(extension)

    return DocumentCandidate(
        url=url,
        filename=filename,
        mime_type=mime_type,
    )


def _deduplicate_candidates(
    candidates: list[DocumentCandidate],
) -> list[DocumentCandidate]:
    result: list[DocumentCandidate] = []
    seen: set[str] = set()

    for candidate in candidates:
        normalized_url = candidate.url.strip()

        if not normalized_url:
            continue

        if normalized_url in seen:
            continue

        seen.add(normalized_url)
        result.append(candidate)

    return result


def _sort_candidates(
    candidates: list[DocumentCandidate],
) -> list[DocumentCandidate]:
    def priority(candidate: DocumentCandidate) -> tuple[int, str]:
        filename = (candidate.filename or urlparse(candidate.url).path or "").lower()

        mime_type = (candidate.mime_type or "").lower()

        if filename.endswith(".pdf") or mime_type == "application/pdf":
            return 0, filename

        if filename.endswith(".docx"):
            return 1, filename

        if filename.endswith(".doc"):
            return 2, filename

        return 3, filename

    return sorted(
        candidates,
        key=priority,
    )


def list_bdu_items(
    client: ResilientHttpClient,
    source: SourceConfig,
    *,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    payload = _get_json(
        client,
        _rest_url(source, "items"),
        params={
            "limit": limit,
            "offset": offset,
        },
    )

    if not isinstance(payload, list):
        raise ValueError(
            f"BDU /rest/items returned an unexpected payload type: {type(payload).__name__}"
        )

    return [item for item in payload if isinstance(item, dict)]


def get_bdu_item(
    client: ResilientHttpClient,
    source: SourceConfig,
    item_id: str | int,
) -> dict[str, Any]:
    payload = _get_json(
        client,
        _rest_url(
            source,
            f"items/{item_id}",
        ),
    )

    if not isinstance(payload, dict):
        raise ValueError(
            f"BDU item endpoint returned an unexpected payload type: {type(payload).__name__}"
        )

    return payload


def get_bdu_metadata(
    client: ResilientHttpClient,
    source: SourceConfig,
    item_id: str | int,
) -> dict[str, Any]:
    payload = _get_json(
        client,
        _rest_url(
            source,
            f"items/{item_id}/metadata",
        ),
    )

    if not isinstance(payload, list):
        raise ValueError(
            f"BDU metadata endpoint returned an unexpected payload type: {type(payload).__name__}"
        )

    rows = [row for row in payload if isinstance(row, dict)]

    return normalize_bdu_metadata(rows)


def get_bdu_bitstreams(
    client: ResilientHttpClient,
    source: SourceConfig,
    item_id: str | int,
) -> list[dict[str, Any]]:
    payload = _get_json(
        client,
        _rest_url(
            source,
            f"items/{item_id}/bitstreams",
        ),
    )

    if not isinstance(payload, list):
        raise ValueError(
            f"BDU bitstreams endpoint returned an unexpected payload type: {type(payload).__name__}"
        )

    return [bitstream for bitstream in payload if isinstance(bitstream, dict)]


def iter_bdu_publications(
    client: ResilientHttpClient,
    source: SourceConfig,
    *,
    max_records: int | None,
    from_date: str | None = None,
    set_spec: str | None = None,
    page_size: int = 100,
) -> Iterator[Publication]:
    del set_spec

    if page_size < 1:
        raise ValueError("page_size must be greater than zero")

    offset = 0
    yielded = 0

    while True:
        items = list_bdu_items(
            client,
            source,
            limit=page_size,
            offset=offset,
        )

        if not items:
            break

        LOGGER.info(
            "BDU REST page: offset=%s, received=%s",
            offset,
            len(items),
        )

        for item in items:
            if max_records is not None and yielded >= max_records:
                return

            if str(item.get("withdrawn", "false")).lower() == "true":
                continue

            if str(item.get("archived", "true")).lower() == "false":
                continue

            item_id = item.get("id")

            if item_id is None:
                continue

            last_modified = str(item.get("lastModified") or "").strip()

            if from_date and last_modified:
                normalized_modified = last_modified.replace(" ", "T")

                if normalized_modified[:10] < from_date:
                    continue

            try:
                metadata = get_bdu_metadata(
                    client,
                    source,
                    item_id,
                )
            except Exception as exc:
                LOGGER.warning(
                    "Unable to retrieve metadata for BDU item %s: %s",
                    item_id,
                    exc,
                )
                metadata = {}

            handle = metadata.get("handle") or item.get("handle")

            landing_url = _repository_handle_url(
                source,
                str(handle) if handle else None,
            )

            if not landing_url:
                landing_url = f"{_base_url(source)}/rest/items/{item_id}"

            title = metadata.get("title") or item.get("name") or f"BDU item {item_id}"

            # For BDU, item_uuid stores the numeric legacy REST item ID.
            # This avoids changing the existing Publication model.
            publication = Publication(
                external_id=f"bdu:{item_id}",
                title=str(title).strip(),
                landing_url=landing_url,
                identifiers=[
                    str(value)
                    for value in (
                        item.get("handle"),
                        metadata.get("handle_uri"),
                        landing_url,
                    )
                    if value
                ],
                item_uuid=str(item_id),
                metadata={
                    "repository": "BDU",
                    "legacy_rest_item_id": str(item_id),
                    "handle": (str(handle) if handle else None),
                    "authors": metadata.get("authors", []),
                    "abstract": metadata.get("abstract"),
                    "subjects": metadata.get("subjects", []),
                    "issued": metadata.get("issued"),
                    "language": metadata.get("language"),
                    "document_type": metadata.get("document_type"),
                    "publisher": metadata.get("publisher"),
                    "last_modified": last_modified or None,
                    "raw_metadata": metadata.get(
                        "raw_metadata",
                        {},
                    ),
                },
            )

            yield publication
            yielded += 1

        offset += len(items)

        if len(items) < page_size:
            break


def _item_id_from_publication(
    publication: Publication,
) -> str | None:
    if publication.item_uuid:
        return str(publication.item_uuid)

    external_id = str(publication.external_id or "")

    if external_id.startswith("bdu:"):
        return external_id.split(":", 1)[1]

    metadata = (
        getattr(
            publication,
            "metadata",
            {},
        )
        or {}
    )

    item_id = metadata.get("legacy_rest_item_id")

    return str(item_id) if item_id is not None else None


def discover_bdu_rest_documents(
    client: ResilientHttpClient,
    source: SourceConfig,
    publication: Publication,
) -> list[DocumentCandidate]:
    item_id = _item_id_from_publication(publication)

    if not item_id:
        return []

    bitstreams = get_bdu_bitstreams(
        client,
        source,
        item_id,
    )

    candidates: list[DocumentCandidate] = []

    for bitstream in bitstreams:
        candidate = _bitstream_candidate(
            source,
            bitstream,
        )

        if candidate:
            candidates.append(candidate)

    return _sort_candidates(_deduplicate_candidates(candidates))


def discover_bdu_html_documents(
    client: ResilientHttpClient,
    source: SourceConfig,
    publication: Publication,
) -> list[DocumentCandidate]:
    """
    HTML fallback is currently disabled.

    BDU document discovery primarily uses:
    /rest/items/{item_id}/bitstreams
    """
    del client
    del source
    del publication

    return []


def discover_bdu_documents(
    client: ResilientHttpClient,
    source: SourceConfig,
    publication: Publication,
) -> list[DocumentCandidate]:
    candidates: list[DocumentCandidate] = []

    try:
        candidates.extend(
            discover_bdu_rest_documents(
                client,
                source,
                publication,
            )
        )
    except Exception as exc:
        LOGGER.warning(
            "BDU REST bitstream discovery failed for %s: %s",
            publication.external_id,
            exc,
        )

    if not candidates:
        LOGGER.info(
            "No BDU REST document found for %s; trying HTML fallback",
            publication.external_id,
        )

        candidates.extend(
            discover_bdu_html_documents(
                client,
                source,
                publication,
            )
        )

    return _sort_candidates(_deduplicate_candidates(candidates))
