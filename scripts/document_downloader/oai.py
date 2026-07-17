from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator

from .http_client import ResilientHttpClient
from .models import Publication, SourceConfig
from .utils import unique

LOGGER = logging.getLogger(__name__)
OAI = "{http://www.openarchives.org/OAI/2.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"


def _text_values(node: ET.Element, tag: str) -> list[str]:
    return unique([element.text or "" for element in node.findall(f".//{DC}{tag}")])


def _choose_landing_url(external_id: str, identifiers: list[str]) -> str | None:
    suffix = external_id.rsplit(":", 1)[-1]
    for identifier in identifiers:
        if identifier.startswith(("http://", "https://")) and identifier.rstrip("/").endswith(
            suffix
        ):
            return identifier
    for identifier in identifiers:
        if identifier.startswith(("http://", "https://")) and (
            "handle" in identifier or "/items/" in identifier
        ):
            return identifier
    return next((value for value in identifiers if value.startswith(("http://", "https://"))), None)


def iter_oai_publications(
    client: ResilientHttpClient,
    source: SourceConfig,
    *,
    max_records: int | None = None,
    from_date: str | None = None,
    set_spec: str | None = None,
) -> Iterator[Publication]:
    token: str | None = None
    seen_tokens: set[str] = set()
    yielded = 0

    while True:
        params: dict[str, str] = {"verb": "ListRecords"}
        if token:
            params["resumptionToken"] = token
        else:
            params["metadataPrefix"] = source.metadata_prefix or "oai_dc"
            if from_date:
                params["from"] = from_date
            if set_spec:
                params["set"] = set_spec

        response = client.request(
            "GET", source.endpoint, params=params, headers={"Accept": "application/xml, text/xml"}
        )
        content = response.content
        response.close()
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise RuntimeError(f"Invalid OAI-PMH XML from {source.endpoint}: {exc}") from exc

        error = root.find(f"{OAI}error")
        if error is not None:
            code = error.attrib.get("code", "unknown")
            message = (error.text or "").strip()
            if code == "noRecordsMatch":
                return
            raise RuntimeError(f"OAI-PMH error {code}: {message}")

        list_records = root.find(f"{OAI}ListRecords")
        if list_records is None:
            raise RuntimeError("OAI-PMH response has no ListRecords element")

        for record in list_records.findall(f"{OAI}record"):
            header = record.find(f"{OAI}header")
            if header is None:
                continue
            external_id = (header.findtext(f"{OAI}identifier") or "").strip()
            if not external_id:
                continue
            if header.attrib.get("status") == "deleted":
                continue
            metadata = record.find(f"{OAI}metadata")
            if metadata is None:
                continue
            titles = _text_values(metadata, "title")
            identifiers = _text_values(metadata, "identifier") + _text_values(metadata, "relation")
            identifiers = unique(identifiers)
            landing_url = _choose_landing_url(external_id, identifiers)
            yield Publication(
                source=source.key,
                external_id=external_id,
                title=titles[0] if titles else None,
                landing_url=landing_url,
                identifiers=identifiers,
                raw={"datestamp": (header.findtext(f"{OAI}datestamp") or "").strip()},
            )
            yielded += 1
            if max_records is not None and yielded >= max_records:
                return

        token_node = list_records.find(f"{OAI}resumptionToken")
        token = (token_node.text or "").strip() if token_node is not None else ""
        if not token:
            return
        if token in seen_tokens:
            raise RuntimeError(f"Repeated OAI-PMH resumption token detected: {token}")
        seen_tokens.add(token)
        LOGGER.info(
            "Following OAI resumption token (cursor=%s, completeListSize=%s)",
            token_node.attrib.get("cursor"),
            token_node.attrib.get("completeListSize"),
        )
