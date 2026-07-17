"""DSpace REST Discovery connector tests."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
from researchhub_harvester.connectors.base import ConnectorConfig
from researchhub_harvester.connectors.dspace_discovery import (
    DSpaceDiscoveryConnector,
    _discovery_endpoint,
)


def dspace_item(identifier: str, title: str, modified: str) -> dict[str, object]:
    return {
        "id": identifier,
        "uuid": identifier,
        "name": title,
        "handle": f"123456789/{identifier}",
        "metadata": {
            "dc.title": [{"value": title}],
            "dc.contributor.author": [{"value": "Kelemework Shimelis"}],
            "dc.date.issued": [{"value": "2023-06"}],
            "dc.description.abstract": [{"value": "Service quality research"}],
            "dc.identifier.uri": [{"value": f"https://example.edu/handle/123456789/{identifier}"}],
            "dc.language.iso": [{"value": "en_US"}],
            "dc.publisher": [{"value": "Addis Ababa University"}],
            "dc.subject": [{"value": "Service Quality"}],
        },
        "inArchive": True,
        "withdrawn": False,
        "lastModified": modified,
        "type": "item",
    }


def discovery_page(
    items: list[dict[str, object]], page: int, total_pages: int
) -> dict[str, object]:
    return {
        "_embedded": {
            "searchResult": {
                "_embedded": {
                    "objects": [{"_embedded": {"indexableObject": item}} for item in items]
                },
                "page": {
                    "number": page,
                    "size": len(items),
                    "totalPages": total_pages,
                    "totalElements": 2,
                },
            }
        }
    }


def connector_with_transport(handler: httpx.MockTransport) -> DSpaceDiscoveryConnector:
    client = httpx.AsyncClient(transport=handler)
    return DSpaceDiscoveryConnector(
        ConnectorConfig(
            code="aau-rest",
            name="AAU REST",
            base_url=(
                "https://example.edu/server/api/discover/search/objects?query=%2A&page=0&size=1"
            ),
            source_type="dspace_discovery",
            extra={"page_size": 100},
        ),
        client=client,
    )


def test_discovery_endpoint_accepts_full_search_or_api_base_urls() -> None:
    full, params = _discovery_endpoint(
        "https://example.edu/server/api/discover/search/objects?query=%2A&page=2&size=1"
    )
    assert full == "https://example.edu/server/api/discover/search/objects"
    assert params == {"query": "*"}
    base, base_params = _discovery_endpoint("https://example.edu/server/api")
    assert base == full
    assert base_params == {"query": "*"}


def test_collect_paginates_filters_incrementally_and_normalizes_dublin_core() -> None:
    requested_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        requested_pages.append(page)
        item = (
            dspace_item("old", "Old record", "2024-01-01T00:00:00Z")
            if page == 0
            else dspace_item("new", "New record", "2026-07-15T12:30:00Z")
        )
        return httpx.Response(200, json=discovery_page([item], page, 2))

    async def run() -> tuple[list[object], DSpaceDiscoveryConnector]:
        connector = connector_with_transport(httpx.MockTransport(handler))
        records = [record async for record in connector.collect(from_date=date(2026, 7, 1))]
        return records, connector

    records, connector = asyncio.run(run())
    assert requested_pages == [0, 1]
    assert len(records) == 1
    publication = connector.normalize(records[0])
    assert publication.external_id == "new"
    assert publication.title == "New record"
    assert publication.authors == ["Kelemework Shimelis"]
    assert publication.publication_year == 2023
    assert publication.abstract == "Service quality research"
    assert publication.subjects == ["Service Quality"]
    assert publication.language == "en"
    assert publication.article_url == "https://example.edu/handle/123456789/new"


def test_identify_reports_dspace_protocol_and_record_count() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=discovery_page([], 0, 0))

    async def run() -> dict[str, object]:
        connector = connector_with_transport(httpx.MockTransport(handler))
        return await connector.identify()

    identity = asyncio.run(run())
    assert identity["protocolVersion"] == "DSpace REST Discovery"
    assert identity["totalElements"] == 2
