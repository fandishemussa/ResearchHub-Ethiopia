"""Reusable enterprise OAI-PMH connector for DSpace, OJS, and compatible archives.

The connector uses ``requests.Session`` for connection pooling, transport retry,
and HTTP keep-alive. It provides synchronous collection methods for harvester
workers and async wrappers to satisfy the platform-wide ``MetadataConnector``
contract.

Supported OAI-PMH features:

* Identify
* ListMetadataFormats
* ListSets
* ListIdentifiers
* ListRecords
* resumptionToken pagination
* incremental harvesting with ``from`` and ``until``
* deleted/tombstone records
* XML import/replay mode
* namespace-aware XML parsing
* Dublin Core metadata normalization
* duplicate detection
* metadata quality scoring
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from time import monotonic
from time import sleep as default_sleep
from typing import Any
from xml.etree import ElementTree as ET

from researchhub_harvester.connectors.base import (
    ConnectorConfig,
    ConnectorError,
    MetadataConnector,
    NormalizedPublication,
    RawRecord,
    TransientConnectorError,
    ValidationIssue,
    ValidationResult,
)
from researchhub_harvester.normalization.quality import quality_score
from researchhub_harvester.normalization.text import (
    normalize_author_name,
    normalize_doi,
    normalize_issn,
    normalize_language,
    normalize_orcid,
    normalize_title,
    normalize_url,
    parse_date,
    parse_year,
    split_terms,
)

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
DC_NS = "http://purl.org/dc/elements/1.1/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"

NS = {"oai": OAI_NS, "dc": DC_NS, "oai_dc": OAI_DC_NS}

DEFAULT_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
CLIENT_ERROR_OAI_CODES = {
    "badArgument",
    "badResumptionToken",
    "badVerb",
    "cannotDisseminateFormat",
    "idDoesNotExist",
    "noMetadataFormats",
    "noSetHierarchy",
}

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass(frozen=True, slots=True)
class ResumptionToken:
    """OAI-PMH resumption token and optional repository-provided cursor metadata."""

    value: str
    complete_list_size: int | None = None
    cursor: int | None = None
    expiration_date: datetime | None = None


@dataclass(frozen=True, slots=True)
class DuplicateKey:
    """Stable publication duplicate key.

    DOI is strongest. If DOI is unavailable, the connector falls back to source
    identifier, then normalized title/year/author text.
    """

    kind: str
    value: str


class OAIPMHConnector(MetadataConnector):
    """Harvest and normalize metadata from OAI-PMH repositories.

    Parameters
    ----------
    config:
        Connector configuration. ``base_url`` must be the OAI-PMH endpoint.
    session:
        Optional injected ``requests.Session``-compatible object. Tests use this
        to avoid network calls. Production callers normally leave it as ``None``.
    sleeper:
        Sleep function used for exponential backoff and rate limiting. Tests can
        inject a no-op or recorder.
    """

    def __init__(
        self,
        config: ConnectorConfig,
        session: Any | None = None,
        sleeper: Callable[[float], None] = default_sleep,
    ) -> None:
        super().__init__(config)
        self.session = session or self._create_session()
        self._owns_session = session is None
        self._sleep = sleeper
        self._last_request_at = 0.0

    async def identify(self) -> dict[str, Any]:
        """Return OAI-PMH Identify metadata through the async connector contract."""

        return self.identify_sync()

    def identify_sync(self) -> dict[str, Any]:
        """Call the OAI-PMH Identify verb and return source capability metadata."""

        root = self._request_sync({"verb": "Identify"})
        identify = root.find("oai:Identify", NS)
        if identify is None:
            msg = "OAI-PMH Identify response did not contain Identify element"
            raise ConnectorError(msg)
        payload = {self._local_name(child.tag): (child.text or "").strip() for child in identify}
        self._log("info", "oai_identify_parsed", fields=sorted(payload))
        return payload

    async def list_metadata_formats(self, identifier: str | None = None) -> list[dict[str, str]]:
        """Return supported metadata formats through the async-compatible API."""

        return self.list_metadata_formats_sync(identifier=identifier)

    def list_metadata_formats_sync(self, identifier: str | None = None) -> list[dict[str, str]]:
        """Return metadata formats supported by the repository."""

        params = {"verb": "ListMetadataFormats"}
        if identifier:
            params["identifier"] = identifier
        root = self._request_sync(params)
        formats: list[dict[str, str]] = []
        for item in root.findall(".//oai:metadataFormat", NS):
            formats.append(
                {
                    "metadataPrefix": self._child_text(item, "metadataPrefix") or "",
                    "schema": self._child_text(item, "schema") or "",
                    "metadataNamespace": self._child_text(item, "metadataNamespace") or "",
                }
            )
        self._log("info", "oai_metadata_formats_parsed", count=len(formats))
        return formats

    async def list_sets(self) -> AsyncIterator[dict[str, str]]:
        """Yield repository sets while following resumption tokens."""

        for item in self.list_sets_sync():
            yield item
            await asyncio.sleep(0)

    def list_sets_sync(self) -> Iterator[dict[str, str]]:
        """Yield repository sets while following resumption tokens."""

        for root in self._paged_request_sync("ListSets", {}):
            for item in root.findall(".//oai:set", NS):
                yield {
                    "setSpec": self._child_text(item, "setSpec") or "",
                    "setName": self._child_text(item, "setName") or "",
                }

    async def list_identifiers(
        self,
        *,
        metadata_prefix: str | None = None,
        from_date: date | datetime | None = None,
        until_date: date | datetime | None = None,
        set_spec: str | None = None,
    ) -> AsyncIterator[RawRecord]:
        """Yield OAI-PMH headers through the async-compatible API."""

        for record in self.list_identifiers_sync(
            metadata_prefix=metadata_prefix,
            from_date=from_date,
            until_date=until_date,
            set_spec=set_spec,
        ):
            yield record
            await asyncio.sleep(0)

    def list_identifiers_sync(
        self,
        *,
        metadata_prefix: str | None = None,
        from_date: date | datetime | None = None,
        until_date: date | datetime | None = None,
        set_spec: str | None = None,
    ) -> Iterator[RawRecord]:
        """Yield OAI-PMH headers without metadata payloads."""

        params = self._list_params(
            metadata_prefix=metadata_prefix,
            from_date=from_date,
            until_date=until_date,
            set_spec=set_spec,
        )
        prefix = metadata_prefix or self.config.metadata_prefix
        for root in self._paged_request_sync("ListIdentifiers", params):
            for header in root.findall(".//oai:ListIdentifiers/oai:header", NS):
                yield self._parse_header_only(header, prefix)

    async def list_records(
        self,
        *,
        metadata_prefix: str | None = None,
        from_date: date | datetime | None = None,
        until_date: date | datetime | None = None,
        set_spec: str | None = None,
    ) -> AsyncIterator[RawRecord]:
        """Yield OAI-PMH records through the async-compatible API."""

        for record in self.list_records_sync(
            metadata_prefix=metadata_prefix,
            from_date=from_date,
            until_date=until_date,
            set_spec=set_spec,
        ):
            yield record
            await asyncio.sleep(0)

    def list_records_sync(
        self,
        *,
        metadata_prefix: str | None = None,
        from_date: date | datetime | None = None,
        until_date: date | datetime | None = None,
        set_spec: str | None = None,
    ) -> Iterator[RawRecord]:
        """Yield OAI-PMH records, following resumption-token pagination."""

        params = self._list_params(
            metadata_prefix=metadata_prefix,
            from_date=from_date,
            until_date=until_date,
            set_spec=set_spec,
        )
        prefix = metadata_prefix or self.config.metadata_prefix
        for root in self._paged_request_sync("ListRecords", params):
            for record in root.findall(".//oai:ListRecords/oai:record", NS):
                yield self._parse_record(record, prefix)

    async def collect(self, **kwargs: Any) -> AsyncIterator[RawRecord]:
        """Collect raw records using configured defaults plus call overrides."""

        for record in self.collect_sync(**kwargs):
            yield record
            await asyncio.sleep(0)

    def collect_sync(self, **kwargs: Any) -> Iterator[RawRecord]:
        """Collect raw records using configured defaults plus call overrides."""

        metadata_prefix = kwargs.get("metadata_prefix") or self.config.metadata_prefix
        from_date = kwargs.get("from_date") or self.config.from_date
        until_date = kwargs.get("until_date") or self.config.until_date
        set_spec = kwargs.get("set_spec") or self.config.set_spec
        yield from self.list_records_sync(
            metadata_prefix=metadata_prefix,
            from_date=from_date,
            until_date=until_date,
            set_spec=set_spec,
        )

    def collect_normalized_sync(
        self, *, deduplicate: bool = True, **kwargs: Any
    ) -> Iterator[NormalizedPublication]:
        """Collect, normalize, validate, and optionally deduplicate publications."""

        publications = (self.normalize(record) for record in self.collect_sync(**kwargs))
        iterable: Iterable[NormalizedPublication] = publications
        if deduplicate:
            iterable = self.deduplicate_publications(iterable)
        for publication in iterable:
            validation = self.validate(publication)
            if validation.valid:
                yield publication
            else:
                self._log(
                    "warning",
                    "oai_publication_validation_failed",
                    identifier=publication.external_id,
                    issues=[
                        {
                            "field": issue.field,
                            "message": issue.message,
                            "severity": issue.severity,
                        }
                        for issue in validation.issues
                    ],
                )

    def import_xml(self, xml_text: str, metadata_prefix: str | None = None) -> list[RawRecord]:
        """Parse previously downloaded OAI-PMH XML into raw records.

        XML import mode is used for replay, audit, recovery after partial
        failures, and unit tests. It accepts complete OAI-PMH responses containing
        records or identifier headers.
        """

        root = self._parse_xml(xml_text)
        prefix = metadata_prefix or self.config.metadata_prefix
        records = [self._parse_record(record, prefix) for record in root.findall(".//oai:record", NS)]
        if records:
            self._log("info", "oai_xml_import_records", count=len(records))
            return records

        headers = [
            self._parse_header_only(header, prefix)
            for header in root.findall(".//oai:header", NS)
        ]
        self._log("info", "oai_xml_import_headers", count=len(headers))
        return headers

    def normalize_xml(
        self, xml_text: str, metadata_prefix: str | None = None, *, deduplicate: bool = True
    ) -> list[NormalizedPublication]:
        """Import OAI-PMH XML and return normalized publications."""

        publications = [self.normalize(record) for record in self.import_xml(xml_text, metadata_prefix)]
        if deduplicate:
            publications = list(self.deduplicate_publications(publications))
        return publications

    def normalize(self, raw_record: RawRecord) -> NormalizedPublication:
        """Normalize Dublin Core metadata into the canonical publication model."""

        now = datetime.now(UTC)
        metadata = raw_record.metadata
        title = normalize_title(self._first(metadata, "title")) or raw_record.identifier
        dates = metadata.get("date", []) + metadata.get("issued", []) + metadata.get("available", [])
        publication_date = next((parsed for parsed in map(parse_date, dates) if parsed), None)
        publication_year = publication_date.year if publication_date else self._first_year(dates)
        author_values = (
            metadata.get("creator", [])
            + metadata.get("author", [])
            + metadata.get("contributor.author", [])
        )
        contributor_values = metadata.get("contributor", [])
        authors = [
            author
            for author in (normalize_author_name(value) for value in author_values)
            if author
        ] or [
            author
            for author in (normalize_author_name(value) for value in contributor_values)
            if author
        ]
        identifiers = (
            metadata.get("identifier", [])
            + metadata.get("relation", [])
            + metadata.get("source", [])
            + metadata.get("bibliographicCitation", [])
        )
        doi = next((value for value in (normalize_doi(item) for item in identifiers) if value), None)
        urls = [value for value in (normalize_url(item) for item in identifiers) if value]
        pdf_url = next((url for url in urls if url.lower().endswith(".pdf")), None)
        article_url = next((url for url in urls if url != pdf_url), None)
        subjects = split_terms(metadata.get("subject", []) + metadata.get("coverage", []))
        keywords = subjects[:]
        language = normalize_language(self._first(metadata, "language"))
        publisher = self._first(metadata, "publisher")
        journal = self._first(metadata, "source") or self._first(metadata, "isPartOf")
        rights = self._first(metadata, "rights") or self._first(metadata, "license")
        issn = next((value for value in (normalize_issn(item) for item in identifiers) if value), None)
        isbn = self._first(metadata, "isbn")
        orcid = next(
            (
                value
                for value in (
                    normalize_orcid(item)
                    for item in author_values + contributor_values + metadata.get("identifier", [])
                )
                if value
            ),
            None,
        )
        record_map = {
            "title": title,
            "authors": authors,
            "publication_year": publication_year,
            "source": self.config.code,
            "source_type": self.config.source_type,
            "doi": doi,
            "abstract": self._first(metadata, "description"),
            "keywords": keywords,
            "language": language,
            "article_url": article_url,
            "is_deleted": raw_record.deleted,
        }
        score, missing_fields, warnings = quality_score(record_map)
        return NormalizedPublication(
            external_id=raw_record.identifier,
            title=title,
            abstract=self._first(metadata, "description"),
            authors=authors,
            affiliations=self._affiliations(metadata),
            journal=journal,
            publisher=publisher,
            publication_date=publication_date,
            publication_year=publication_year,
            keywords=keywords,
            subjects=subjects,
            language=language,
            doi=doi,
            orcid=orcid,
            issn=issn,
            isbn=isbn,
            license=rights,
            article_url=article_url,
            pdf_url=pdf_url,
            repository=self.config.name,
            repository_identifier=raw_record.identifier,
            source=self.config.code,
            source_type=self.config.source_type,
            harvested_at=now,
            updated_at=raw_record.datestamp or now,
            quality_score=score,
            is_deleted=raw_record.deleted,
            raw_record={
                "header": raw_record.header,
                "metadata": raw_record.metadata,
                "set_specs": raw_record.set_specs,
                "raw_xml": raw_record.raw_xml,
                "metadata_quality": {
                    "score": score,
                    "missing_fields": missing_fields,
                    "warnings": warnings,
                },
            },
        )

    def validate(self, publication: NormalizedPublication) -> ValidationResult:
        """Validate normalized publication completeness before persistence."""

        issues: list[ValidationIssue] = []
        if not publication.title:
            issues.append(ValidationIssue("title", "Publication title is required", "error"))
        if not publication.external_id:
            issues.append(ValidationIssue("external_id", "Source identifier is required", "error"))
        if not publication.authors and not publication.is_deleted:
            issues.append(ValidationIssue("authors", "No authors found"))
        if not publication.publication_year and not publication.is_deleted:
            issues.append(ValidationIssue("publication_year", "No publication year found"))
        return ValidationResult(
            valid=not any(issue.severity == "error" for issue in issues),
            issues=issues,
        )

    def duplicate_key(self, publication: NormalizedPublication) -> DuplicateKey:
        """Return the strongest available duplicate key for a normalized record."""

        if publication.doi:
            return DuplicateKey("doi", publication.doi.casefold())
        if publication.external_id:
            return DuplicateKey("source_identifier", f"{publication.source}:{publication.external_id}")
        title = " ".join(publication.title.casefold().split())
        authors = "|".join(author.casefold() for author in publication.authors[:3])
        return DuplicateKey("title_year_authors", f"{title}:{publication.publication_year or ''}:{authors}")

    def deduplicate_publications(
        self, publications: Iterable[NormalizedPublication]
    ) -> Iterator[NormalizedPublication]:
        """Yield publications once according to DOI/source/title duplicate keys."""

        seen: set[DuplicateKey] = set()
        for publication in publications:
            key = self.duplicate_key(publication)
            if key in seen:
                self._log(
                    "info",
                    "oai_duplicate_publication_skipped",
                    duplicate_key=key.value,
                    duplicate_kind=key.kind,
                    identifier=publication.external_id,
                )
                continue
            seen.add(key)
            yield publication

    def export(
        self, publications: Iterable[NormalizedPublication], *, deduplicate: bool = True
    ) -> list[dict[str, Any]]:
        """Export normalized publications as dictionaries ready for persistence."""

        iterable = self.deduplicate_publications(publications) if deduplicate else publications
        return [publication.asdict() for publication in iterable]

    def close(self) -> None:
        """Close the owned ``requests.Session`` connection pool."""

        if self._owns_session and hasattr(self.session, "close"):
            self.session.close()

    async def aclose(self) -> None:
        """Async-compatible close hook for callers using the connector contract."""

        self.close()

    def _create_session(self) -> Any:
        """Create a pooled requests session with retry-enabled HTTP adapters."""

        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
        except ImportError as exc:
            msg = "The requests package is required for OAIPMHConnector"
            raise ConnectorError(msg) from exc

        session = requests.Session()
        retry = Retry(
            total=self.config.max_retries,
            connect=self.config.max_retries,
            read=self.config.max_retries,
            status=self.config.max_retries,
            allowed_methods=frozenset({"GET"}),
            status_forcelist=DEFAULT_RETRY_STATUS_CODES,
            backoff_factor=float(self.config.extra.get("backoff_factor", self.config.backoff_factor)),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=int(self.config.extra.get("pool_connections", self.config.pool_connections)),
            pool_maxsize=int(self.config.extra.get("pool_maxsize", self.config.pool_maxsize)),
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _paged_request_sync(self, verb: str, params: dict[str, str]) -> Iterator[ET.Element]:
        """Yield response roots while following OAI-PMH resumption tokens."""

        next_params = {"verb": verb, **params}
        page = 0
        while True:
            root = self._request_sync(next_params)
            yield root
            page += 1
            token = self._resumption_token(root, verb)
            if not token:
                self._log("info", "oai_pagination_finished", verb=verb, pages=page)
                break
            self._log(
                "info",
                "oai_resumption_token_received",
                verb=verb,
                page=page,
                cursor=token.cursor,
                complete_list_size=token.complete_list_size,
            )
            next_params = {"verb": verb, "resumptionToken": token.value}

    def _list_params(
        self,
        *,
        metadata_prefix: str | None,
        from_date: date | datetime | None,
        until_date: date | datetime | None,
        set_spec: str | None,
    ) -> dict[str, str]:
        """Build OAI list parameters from connector defaults and overrides."""

        params = {"metadataPrefix": metadata_prefix or self.config.metadata_prefix}
        if from_date:
            params["from"] = self._format_oai_date(from_date)
        if until_date:
            params["until"] = self._format_oai_date(until_date)
        if set_spec:
            params["set"] = set_spec
        return params

    def _request_sync(self, params: dict[str, str]) -> ET.Element:
        """Execute an OAI-PMH request with pooling, retry, and backoff."""

        headers = {"User-Agent": self.config.user_agent, **self.config.headers}
        attempts = max(1, self.config.max_retries)
        for attempt in range(1, attempts + 1):
            self._respect_rate_limit()
            try:
                self._log(
                    "info",
                    "oai_request_started",
                    verb=params.get("verb"),
                    attempt=attempt,
                    params=self._safe_params(params),
                )
                response = self.session.get(
                    self.config.base_url,
                    params=params,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                status_code = int(getattr(response, "status_code", 0))
                text = getattr(response, "text", "")
                if status_code in DEFAULT_RETRY_STATUS_CODES:
                    raise TransientConnectorError(f"Provider returned HTTP {status_code}")
                if 400 <= status_code < 500:
                    raise ConnectorError(f"Provider returned HTTP {status_code}")
                root = self._parse_xml(text)
                self._raise_for_oai_error(root)
                self._log(
                    "info",
                    "oai_request_succeeded",
                    verb=params.get("verb"),
                    attempt=attempt,
                    status_code=status_code,
                )
                return root
            except TransientConnectorError as exc:
                if attempt >= attempts:
                    self._log("error", "oai_request_retry_exhausted", error=str(exc), attempt=attempt)
                    raise
                self._backoff(attempt, str(exc))
            except ConnectorError:
                raise
            except Exception as exc:  # noqa: BLE001 - provider clients raise varied transport errors.
                if attempt >= attempts:
                    self._log("error", "oai_request_failed", error=str(exc), attempt=attempt)
                    raise TransientConnectorError(str(exc)) from exc
                self._backoff(attempt, str(exc))
        msg = "unreachable OAI request retry loop exit"
        raise TransientConnectorError(msg)

    def _parse_xml(self, xml_text: str) -> ET.Element:
        """Parse XML text into an ElementTree root with connector errors."""

        try:
            return ET.fromstring(xml_text)
        except ET.ParseError as exc:
            msg = f"Invalid OAI-PMH XML: {exc}"
            raise ConnectorError(msg) from exc

    def _respect_rate_limit(self) -> None:
        """Throttle outbound requests according to connector configuration."""

        if self.config.rate_limit_per_second <= 0:
            return
        interval = 1.0 / self.config.rate_limit_per_second
        elapsed = monotonic() - self._last_request_at
        if elapsed < interval:
            self._sleep(interval - elapsed)
        self._last_request_at = monotonic()

    def _backoff(self, attempt: int, error: str) -> None:
        """Sleep for an exponential backoff interval before a retry."""

        base = float(self.config.extra.get("backoff_factor", self.config.backoff_factor))
        cap = float(self.config.extra.get("max_backoff_seconds", self.config.max_backoff_seconds))
        delay = min(base * (2 ** (attempt - 1)), cap)
        self._log("warning", "oai_request_retrying", attempt=attempt, delay=delay, error=error)
        self._sleep(delay)

    def _raise_for_oai_error(self, root: ET.Element) -> None:
        """Raise connector errors for OAI-PMH error responses."""

        errors = root.findall("oai:error", NS)
        for error in errors:
            code = error.attrib.get("code", "unknown")
            message = (error.text or "").strip()
            if code == "noRecordsMatch":
                self._log("info", "oai_no_records_match", message=message)
                continue
            if code in CLIENT_ERROR_OAI_CODES:
                raise ConnectorError(f"OAI-PMH error {code}: {message}")
            raise TransientConnectorError(f"OAI-PMH error {code}: {message}")

    def _parse_record(self, record: ET.Element, metadata_prefix: str) -> RawRecord:
        """Parse an OAI-PMH ``record`` element."""

        header = record.find("oai:header", NS)
        if header is None:
            msg = "OAI-PMH record is missing header"
            raise ConnectorError(msg)
        raw_xml = ET.tostring(record, encoding="unicode")
        parsed = self._parse_header_only(header, metadata_prefix)
        metadata_element = record.find("oai:metadata", NS)
        parsed.metadata = self._parse_metadata(metadata_element)
        parsed.raw_xml = raw_xml
        return parsed

    def _parse_header_only(self, header: ET.Element, metadata_prefix: str) -> RawRecord:
        """Parse an OAI-PMH header into a raw record shell."""

        identifier = self._child_text(header, "identifier")
        if not identifier:
            msg = "OAI-PMH header is missing identifier"
            raise ConnectorError(msg)
        datestamp = self._parse_datestamp(self._child_text(header, "datestamp"))
        set_specs = [
            (item.text or "").strip()
            for item in header.findall("oai:setSpec", NS)
            if (item.text or "").strip()
        ]
        return RawRecord(
            identifier=identifier,
            datestamp=datestamp,
            deleted=header.attrib.get("status") == "deleted",
            metadata={},
            header={
                "identifier": identifier,
                "datestamp": datestamp.isoformat() if datestamp else None,
                "status": header.attrib.get("status"),
            },
            set_specs=set_specs,
            source=self.config.code,
            metadata_prefix=metadata_prefix,
        )

    def _parse_metadata(self, metadata_element: ET.Element | None) -> dict[str, list[str]]:
        """Parse namespaced Dublin Core metadata into a multimap."""

        values: dict[str, list[str]] = defaultdict(list)
        if metadata_element is None:
            return {}
        for element in metadata_element.iter():
            local = self._local_name(element.tag)
            if local in {"metadata", "dc"}:
                continue
            text = (element.text or "").strip()
            if text:
                values[local].append(text)
        return dict(values)

    def _resumption_token(self, root: ET.Element, verb: str) -> ResumptionToken | None:
        """Return the resumption token for a list response, if present."""

        container = root.find(f"oai:{verb}", NS)
        if container is None:
            return None
        token = container.find("oai:resumptionToken", NS)
        value = (token.text or "").strip() if token is not None else ""
        if not value:
            return None
        return ResumptionToken(
            value=value,
            complete_list_size=self._parse_int(token.attrib.get("completeListSize")),
            cursor=self._parse_int(token.attrib.get("cursor")),
            expiration_date=self._parse_datestamp(token.attrib.get("expirationDate")),
        )

    def _parse_datestamp(self, value: str | None) -> datetime | None:
        """Parse OAI-PMH datestamps in date or datetime form."""

        if not value:
            return None
        try:
            if "T" in value:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            parsed_date = date.fromisoformat(value)
            return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
        except ValueError:
            return None

    def _format_oai_date(self, value: date | datetime) -> str:
        """Format date or datetime values for OAI-PMH incremental harvesting."""

        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return value.isoformat()

    def _child_text(self, element: ET.Element, child_name: str) -> str | None:
        """Return stripped text for a direct OAI child element."""

        child = element.find(f"oai:{child_name}", NS)
        value = (child.text or "").strip() if child is not None else ""
        return value or None

    def _local_name(self, tag: str) -> str:
        """Return the local XML name without namespace."""

        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    def _first(self, metadata: dict[str, list[str]], key: str) -> str | None:
        """Return the first non-empty metadata value for a key."""

        return next((value for value in metadata.get(key, []) if value), None)

    def _first_year(self, values: list[str]) -> int | None:
        """Return the first plausible year from a list of date values."""

        return next((year for year in (parse_year(value) for value in values) if year), None)

    def _affiliations(self, metadata: dict[str, list[str]]) -> list[str]:
        """Extract affiliation-like metadata from common repository fields."""

        return [
            value
            for value in (
                metadata.get("affiliation", [])
                + metadata.get("contributor.department", [])
                + metadata.get("description.sponsorship", [])
            )
            if value
        ]

    def _parse_int(self, value: str | None) -> int | None:
        """Parse an optional integer attribute."""

        try:
            return int(value) if value else None
        except ValueError:
            return None

    def _safe_params(self, params: dict[str, str]) -> dict[str, str]:
        """Return request parameters safe for logs."""

        return {key: value for key, value in params.items() if key != "resumptionToken"} | (
            {"resumptionToken": "***"} if "resumptionToken" in params else {}
        )

    def _log(self, level: str, event: str, **context: Any) -> None:
        """Emit structured logging context for harvester observability."""

        payload = {
            "event": event,
            "connector": self.config.code,
            "source_type": self.config.source_type,
            "base_url": self.config.base_url,
            **context,
        }
        log_fn = getattr(logger, level, logger.info)
        log_fn(event, extra={"researchhub": payload})
