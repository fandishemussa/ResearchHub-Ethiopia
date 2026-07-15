"""Comprehensive tests for the reusable OAI-PMH connector."""

from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harvester"))

from researchhub_harvester.connectors.base import ConnectorConfig, ConnectorError  # noqa: E402
from researchhub_harvester.connectors.oai_pmh import OAIPMHConnector  # noqa: E402


def envelope(body: str) -> str:
    """Wrap an OAI-PMH response body with common namespaces."""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <responseDate>2026-07-11T00:00:00Z</responseDate>
  <request>https://repo.example.edu/oai</request>
  {body}
</OAI-PMH>
"""


def record_xml(identifier: str, title: str, doi: str = "10.1234/RHE.2025.001") -> str:
    """Return a representative DSpace/OJS Dublin Core record."""

    return f"""
    <record>
      <header>
        <identifier>{identifier}</identifier>
        <datestamp>2025-06-01</datestamp>
        <setSpec>com_123456789_1</setSpec>
      </header>
      <metadata>
        <oai_dc:dc>
          <dc:title> {title} </dc:title>
          <dc:creator>Lemma, Tesfaye</dc:creator>
          <dc:subject>soil; agriculture; Ethiopia</dc:subject>
          <dc:description>Study of soil fertility interventions.</dc:description>
          <dc:publisher>Haramaya University</dc:publisher>
          <dc:date>2025-05-20</dc:date>
          <dc:type>Article</dc:type>
          <dc:identifier>https://doi.org/{doi}</dc:identifier>
          <dc:identifier>https://repo.example.edu/bitstream/123/1/article.pdf</dc:identifier>
          <dc:source>Haramaya Journal of Agriculture</dc:source>
          <dc:language>English</dc:language>
          <dc:rights>CC BY 4.0</dc:rights>
        </oai_dc:dc>
      </metadata>
    </record>
"""


SAMPLE_XML = envelope(
    f"""
  <ListRecords>
    {record_xml("oai:repo.example.edu:123", "Soil fertility management in eastern Ethiopia")}
    <record>
      <header status="deleted">
        <identifier>oai:repo.example.edu:deleted</identifier>
        <datestamp>2025-06-02</datestamp>
      </header>
    </record>
  </ListRecords>
"""
)


@dataclass(slots=True)
class FakeResponse:
    """Small response object compatible with the connector's session usage."""

    text: str
    status_code: int = 200


class FakeSession:
    """requests.Session-like fake that records calls and returns queued responses."""

    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []
        self.closed = False

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        """Record request details and return or raise the next queued result."""

        self.requests.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError("No fake response queued")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self) -> None:
        """Mark the fake session closed."""

        self.closed = True


class OAIPMHConnectorTests(unittest.TestCase):
    """Verify parser, transport, pagination, and normalization behavior."""

    def connector(
        self,
        responses: list[FakeResponse | Exception] | None = None,
        sleeps: list[float] | None = None,
        *,
        max_retries: int = 3,
    ) -> OAIPMHConnector:
        """Create a connector with a fake session and no rate-limit sleep."""

        config = ConnectorConfig(
            code="haramaya-ir",
            name="Haramaya Institutional Repository",
            base_url="https://repo.example.edu/oai",
            source_type="oai-pmh",
            max_retries=max_retries,
            backoff_factor=0.25,
            rate_limit_per_second=0,
        )
        return OAIPMHConnector(
            config,
            session=FakeSession(responses or []),
            sleeper=(sleeps.append if sleeps is not None else (lambda seconds: None)),
        )

    def test_import_xml_and_normalize_record(self) -> None:
        """Dublin Core records normalize into the canonical publication model."""

        connector = self.connector()
        records = connector.import_xml(SAMPLE_XML)
        self.assertEqual(len(records), 2)
        publication = connector.normalize(records[0])

        self.assertEqual(publication.external_id, "oai:repo.example.edu:123")
        self.assertEqual(publication.title, "Soil fertility management in eastern Ethiopia")
        self.assertEqual(publication.authors, ["Tesfaye Lemma"])
        self.assertEqual(publication.publication_year, 2025)
        self.assertEqual(publication.doi, "10.1234/rhe.2025.001")
        self.assertEqual(publication.language, "en")
        self.assertEqual(publication.journal, "Haramaya Journal of Agriculture")
        self.assertTrue(publication.pdf_url.endswith("article.pdf"))
        self.assertGreater(publication.quality_score, 80)
        self.assertIn("metadata_quality", publication.raw_record)

    def test_deleted_record_is_preserved(self) -> None:
        """Deleted OAI records stay visible for downstream tombstone handling."""

        connector = self.connector()
        deleted_record = connector.import_xml(SAMPLE_XML)[1]
        publication = connector.normalize(deleted_record)

        self.assertTrue(deleted_record.deleted)
        self.assertTrue(publication.is_deleted)
        self.assertEqual(publication.repository_identifier, "oai:repo.example.edu:deleted")

    def test_identify_metadata_formats_sets_and_identifiers(self) -> None:
        """Repository discovery verbs parse namespace-aware OAI-PMH XML."""

        connector = self.connector(
            [
                FakeResponse(
                    envelope(
                        """
  <Identify>
    <repositoryName>Example Repository</repositoryName>
    <baseURL>https://repo.example.edu/oai</baseURL>
    <deletedRecord>persistent</deletedRecord>
  </Identify>
"""
                    )
                ),
                FakeResponse(
                    envelope(
                        """
  <ListMetadataFormats>
    <metadataFormat>
      <metadataPrefix>oai_dc</metadataPrefix>
      <schema>http://www.openarchives.org/OAI/2.0/oai_dc.xsd</schema>
      <metadataNamespace>http://www.openarchives.org/OAI/2.0/oai_dc/</metadataNamespace>
    </metadataFormat>
  </ListMetadataFormats>
"""
                    )
                ),
                FakeResponse(
                    envelope(
                        """
  <ListSets>
    <set><setSpec>com_1</setSpec><setName>Articles</setName></set>
  </ListSets>
"""
                    )
                ),
                FakeResponse(
                    envelope(
                        """
  <ListIdentifiers>
    <header>
      <identifier>oai:repo.example.edu:1</identifier>
      <datestamp>2025-01-01</datestamp>
    </header>
  </ListIdentifiers>
"""
                    )
                ),
            ]
        )

        self.assertEqual(connector.identify_sync()["repositoryName"], "Example Repository")
        self.assertEqual(connector.list_metadata_formats_sync()[0]["metadataPrefix"], "oai_dc")
        self.assertEqual(list(connector.list_sets_sync())[0]["setName"], "Articles")
        identifiers = list(connector.list_identifiers_sync())
        self.assertEqual(identifiers[0].identifier, "oai:repo.example.edu:1")

    def test_pagination_resumption_token_and_incremental_harvest_params(self) -> None:
        """ListRecords follows resumption tokens and sends incremental parameters."""

        first_page = envelope(
            f"""
  <ListRecords>
    {record_xml("oai:repo.example.edu:1", "First page", "10.1234/RHE.1")}
    <resumptionToken completeListSize="2" cursor="0">TOKEN-1</resumptionToken>
  </ListRecords>
"""
        )
        second_page = envelope(
            f"""
  <ListRecords>
    {record_xml("oai:repo.example.edu:2", "Second page", "10.1234/RHE.2")}
  </ListRecords>
"""
        )
        connector = self.connector([FakeResponse(first_page), FakeResponse(second_page)])

        records = list(
            connector.list_records_sync(
                from_date=date(2025, 1, 1),
                until_date=date(2025, 12, 31),
                set_spec="com_123456789_1",
            )
        )

        self.assertEqual([record.identifier for record in records], ["oai:repo.example.edu:1", "oai:repo.example.edu:2"])
        session = connector.session
        self.assertEqual(session.requests[0]["params"]["from"], "2025-01-01")
        self.assertEqual(session.requests[0]["params"]["until"], "2025-12-31")
        self.assertEqual(session.requests[0]["params"]["set"], "com_123456789_1")
        self.assertEqual(session.requests[1]["params"], {"verb": "ListRecords", "resumptionToken": "TOKEN-1"})

    def test_retry_strategy_uses_exponential_backoff(self) -> None:
        """Transient HTTP failures retry with exponential backoff."""

        sleeps: list[float] = []
        connector = self.connector(
            [
                FakeResponse("service unavailable", status_code=503),
                FakeResponse(
                    envelope(
                        """
  <Identify><repositoryName>Recovered Repository</repositoryName></Identify>
"""
                    )
                ),
            ],
            sleeps=sleeps,
            max_retries=2,
        )

        self.assertEqual(connector.identify_sync()["repositoryName"], "Recovered Repository")
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(len(connector.session.requests), 2)

    def test_oai_errors_and_malformed_xml_are_reported(self) -> None:
        """OAI client errors and invalid XML fail with connector exceptions."""

        connector = self.connector(
            [
                FakeResponse(
                    envelope(
                        """
  <error code="badArgument">Bad request</error>
"""
                    )
                )
            ]
        )
        with self.assertRaises(ConnectorError):
            connector.identify_sync()

        with self.assertRaises(ConnectorError):
            self.connector().import_xml("<OAI-PMH>")

    def test_no_records_match_returns_empty_collection(self) -> None:
        """The OAI noRecordsMatch response is not treated as a failed harvest."""

        connector = self.connector(
            [
                FakeResponse(
                    envelope(
                        """
  <error code="noRecordsMatch">No records match</error>
"""
                    )
                )
            ]
        )

        self.assertEqual(list(connector.list_records_sync()), [])

    def test_duplicate_detection_deduplicates_by_doi(self) -> None:
        """Export and XML normalization remove duplicate DOI records."""

        connector = self.connector()
        xml = envelope(
            f"""
  <ListRecords>
    {record_xml("oai:repo.example.edu:a", "Duplicate A", "10.1234/DUP")}
    {record_xml("oai:repo.example.edu:b", "Duplicate B", "10.1234/DUP")}
  </ListRecords>
"""
        )

        publications = connector.normalize_xml(xml)
        self.assertEqual(len(publications), 1)
        exported = connector.export(publications + publications)
        self.assertEqual(len(exported), 1)

    def test_async_collect_wrapper_uses_sync_session_core(self) -> None:
        """The async connector contract remains usable by existing harvest runners."""

        connector = self.connector([FakeResponse(SAMPLE_XML)])

        async def collect_ids() -> list[str]:
            return [record.identifier async for record in connector.collect()]

        self.assertEqual(
            asyncio.run(collect_ids()),
            ["oai:repo.example.edu:123", "oai:repo.example.edu:deleted"],
        )

    def test_close_closes_owned_session_only(self) -> None:
        """Injected sessions are caller-owned and should not be closed by connector."""

        fake_session = FakeSession([])
        config = ConnectorConfig(
            code="haramaya-ir",
            name="Haramaya Institutional Repository",
            base_url="https://repo.example.edu/oai",
            source_type="oai-pmh",
        )
        connector = OAIPMHConnector(config, session=fake_session)
        connector.close()
        self.assertFalse(fake_session.closed)


if __name__ == "__main__":
    unittest.main()

