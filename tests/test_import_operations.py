"""Metadata import parsing and safety tests."""

import json
from uuid import uuid4

import pytest
from researchhub.application.import_operations import (
    _normalize_mapping,
    _parse_records,
    _parse_records_with_errors,
)
from researchhub.infrastructure.persistence.models import Connector


def source() -> Connector:
    return Connector(
        id=uuid4(),
        code="test-source",
        name="Test Source",
        connector_type="json_import",
        university_id=uuid4(),
        metadata_prefix="oai_dc",
    )


def test_json_list_is_normalized_with_source_provenance() -> None:
    payload = json.dumps(
        [
            {
                "external_id": "record-1",
                "title": "Maternal health services",
                "abstract": "Evidence from eastern Ethiopia.",
                "authors": ["Aster Bekele"],
                "subjects": ["Maternal health"],
                "publication_year": 2024,
            }
        ]
    ).encode()
    records = _parse_records(payload, "json", source())
    assert len(records) == 1
    assert records[0].source == "test-source"
    assert records[0].authors == ["Aster Bekele"]
    assert records[0].publication_year == 2024


def test_csv_headers_map_authors_and_keywords() -> None:
    payload = b"external_id,title,authors,year,keywords\n1,Water quality,Aster Bekele;Lemma Ali,2023,water;health\n"
    record = _parse_records(payload, "csv", source())[0]
    assert record.authors == ["Aster Bekele", "Lemma Ali"]
    assert record.keywords == ["water", "health"]


def test_missing_title_is_rejected() -> None:
    with pytest.raises(ValueError, match="title"):
        _normalize_mapping({"external_id": "missing-title"}, source())


def test_bulk_import_skips_invalid_rows_instead_of_rejecting_file() -> None:
    payload = json.dumps([{"title": "Valid record"}, {"external_id": "missing-title"}]).encode()
    records, errors, total = _parse_records_with_errors(payload, "json", source())
    assert total == 2
    assert [record.title for record in records] == ["Valid record"]
    assert errors == [{"record_index": 1, "message": "A record is missing its title"}]


def test_dspace_metadata_title_and_authors_are_supported() -> None:
    record = _normalize_mapping(
        {
            "uuid": "item-1",
            "name": "Fallback item name",
            "metadata": {
                "dc.title": [{"value": "Metadata title"}],
                "dc.contributor.author": [{"value": "Aster Bekele"}],
                "dc.date.issued": [{"value": "2024-06"}],
            },
        },
        source(),
    )
    assert record.title == "Metadata title"
    assert record.authors == ["Aster Bekele"]
    assert record.publication_year == 2024


def test_unsupported_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        _parse_records(b"content", "exe", source())
