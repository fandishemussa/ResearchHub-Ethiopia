"""DSpace 7 REST Discovery connector with HAL pagination."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx

from researchhub_harvester.connectors.base import (
    ConnectorConfig,
    ConnectorError,
    MetadataConnector,
    RawRecord,
    TransientConnectorError,
)
from researchhub_harvester.connectors.oai_pmh import OAIPMHConnector

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
METADATA_ALIASES = {
    "date.issued": "issued",
    "date.available": "available",
    "description.abstract": "description",
    "identifier.uri": "identifier",
    "language.iso": "language",
    "rights.license": "license",
}


class DSpaceDiscoveryConnector(OAIPMHConnector):
    """Harvest DSpace items from ``/api/discover/search/objects``.

    Dublin Core normalization, quality validation, and export behavior are
    inherited from the mature OAI connector. Only transport and HAL parsing
    are DSpace-specific.
    """

    def __init__(
        self,
        config: ConnectorConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        MetadataConnector.__init__(self, config)
        self.search_url, self.search_params = _discovery_endpoint(config.base_url)
        headers = {"Accept": "application/hal+json", **config.headers}
        headers.setdefault("User-Agent", config.user_agent)
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=True,
            headers=headers,
        )
        self._owns_client = client is None

    async def identify(self) -> dict[str, Any]:
        """Return DSpace identity and indexed-record count."""

        payload = await self._request_page(0, 1)
        result = _search_result(payload)
        page = result.get("page") or {}
        return {
            "repositoryName": self.config.name,
            "protocolVersion": "DSpace REST Discovery",
            "baseURL": self.search_url,
            "totalElements": int(page.get("totalElements") or 0),
            "totalPages": int(page.get("totalPages") or 0),
        }

    async def collect(self, **kwargs: Any) -> AsyncIterator[RawRecord]:
        """Yield normalized raw records while following DSpace HAL pages."""

        from_date = _as_date(kwargs.get("from_date") or self.config.from_date)
        until_date = _as_date(kwargs.get("until_date") or self.config.until_date)
        maximum_records = self.config.extra.get("maximum_records")
        maximum = int(maximum_records) if maximum_records else None
        configured_page_size = int(self.config.extra.get("page_size", 25))
        page_size = max(1, min(configured_page_size, 100, maximum or 100))
        include_deleted = bool(self.config.extra.get("include_deleted_records", True))
        emitted = 0
        page_number = 0

        while True:
            payload = await self._request_page(page_number, page_size)
            result = _search_result(payload)
            objects = (result.get("_embedded") or {}).get("objects") or []
            for wrapper in objects:
                item = (wrapper.get("_embedded") or {}).get("indexableObject") or {}
                if not item or item.get("type") != "item":
                    continue
                raw = _raw_record(item, self.config)
                modified = raw.datestamp.date() if raw.datestamp else None
                if from_date and (modified is None or modified < from_date):
                    continue
                if until_date and (modified is None or modified > until_date):
                    continue
                if raw.deleted and not include_deleted:
                    continue
                yield raw
                emitted += 1
                if maximum is not None and emitted >= maximum:
                    return

            page = result.get("page") or {}
            total_pages = int(page.get("totalPages") or 0)
            if not objects or page_number + 1 >= total_pages:
                return
            page_number += 1

    async def _request_page(self, page: int, size: int) -> dict[str, Any]:
        params = {**self.search_params, "page": str(page), "size": str(size)}
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.get(self.search_url, params=params)
                if response.status_code in RETRY_STATUS_CODES:
                    raise TransientConnectorError(
                        f"DSpace returned retryable HTTP {response.status_code}"
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ConnectorError("DSpace returned a non-object JSON response")
                return payload
            except (httpx.TimeoutException, httpx.NetworkError, TransientConnectorError) as exc:
                if attempt >= self.config.max_retries:
                    raise TransientConnectorError(
                        f"DSpace request failed after {attempt + 1} attempts"
                    ) from exc
                delay = min(
                    self.config.max_backoff_seconds,
                    self.config.backoff_factor * (2**attempt),
                )
                await asyncio.sleep(delay)
            except (httpx.HTTPStatusError, ValueError) as exc:
                raise ConnectorError(f"Invalid DSpace Discovery response: {exc}") from exc
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


def _discovery_endpoint(value: str) -> tuple[str, dict[str, str]]:
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/")
    if not path.endswith("/discover/search/objects"):
        if path.endswith("/server/api") or path.endswith("/api"):
            path = f"{path}/discover/search/objects"
        else:
            path = f"{path}/server/api/discover/search/objects"
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.pop("page", None)
    params.pop("size", None)
    params.setdefault("query", "*")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")), params


def _search_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = (payload.get("_embedded") or {}).get("searchResult") or {}
    if not isinstance(result, dict):
        raise ConnectorError("DSpace response is missing _embedded.searchResult")
    return result


def _raw_record(item: dict[str, Any], config: ConnectorConfig) -> RawRecord:
    identifier = str(item.get("uuid") or item.get("id") or item.get("handle") or "").strip()
    if not identifier:
        raise ConnectorError("DSpace item is missing its identifier")
    metadata = _metadata_values(item.get("metadata") or {})
    if not metadata.get("title") and item.get("name"):
        metadata["title"] = [str(item["name"])]
    if item.get("handle"):
        handle_url = _handle_url(config.base_url, str(item["handle"]))
        metadata.setdefault("identifier", []).append(handle_url)
    modified = _parse_datetime(item.get("lastModified"))
    deleted = bool(item.get("withdrawn")) or not bool(item.get("inArchive", True))
    return RawRecord(
        identifier=identifier,
        datestamp=modified,
        deleted=deleted,
        metadata=metadata,
        header={
            "id": item.get("id"),
            "uuid": item.get("uuid"),
            "handle": item.get("handle"),
            "lastModified": item.get("lastModified"),
            "withdrawn": item.get("withdrawn"),
            "inArchive": item.get("inArchive"),
        },
        source=config.code,
        metadata_prefix="dspace_dc",
    )


def _metadata_values(metadata: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for raw_key, raw_values in metadata.items():
        key = str(raw_key).removeprefix("dc.")
        key = METADATA_ALIASES.get(key, key)
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        cleaned = [
            str(value.get("value") if isinstance(value, dict) else value).strip()
            for value in values
            if value is not None and (not isinstance(value, dict) or value.get("value") is not None)
        ]
        cleaned = [value for value in cleaned if value]
        if key == "language":
            cleaned = [value.replace("_", "-").split("-", 1)[0] for value in cleaned]
        if cleaned:
            result.setdefault(key, []).extend(cleaned)
    return result


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _handle_url(base_url: str, handle: str) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/handle/{handle}", "", ""))
