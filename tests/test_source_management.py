"""Source-management validation, security, and connection tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from researchhub.application.source_management import (
    _sanitize_for_storage,
)
from researchhub.application.source_management import (
    test_source_configuration as run_connection_test,
)
from researchhub.domain.schemas import SourceCreate, SourceRead
from researchhub.infrastructure.persistence.models import Connector


def source_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "university_id": uuid4(),
        "name": "AAU ETD",
        "slug": "aau-etd",
        "source_type": "dspace_oai",
        "oai_endpoint": "https://example.edu/oai/request",
        "metadata_prefix": "oai_dc",
    }
    payload.update(changes)
    return payload


def test_source_schema_validates_slug_type_and_metadata_prefix() -> None:
    assert SourceCreate.model_validate(source_payload()).slug == "aau-etd"
    with pytest.raises(ValidationError):
        SourceCreate.model_validate(source_payload(slug="Unsafe Slug"))
    with pytest.raises(ValidationError):
        SourceCreate.model_validate(source_payload(source_type="shell"))
    with pytest.raises(ValidationError):
        SourceCreate.model_validate(source_payload(metadata_prefix="bad prefix"))


def test_source_response_never_contains_connection_secrets() -> None:
    source = Connector(
        id=uuid4(),
        university_id=uuid4(),
        code="aau-etd",
        name="AAU ETD",
        connector_type="dspace_oai",
        oai_endpoint="https://example.edu/oai/request",
        metadata_prefix="oai_dc",
        supported_formats=["oai_dc"],
        enabled=True,
        is_public=True,
        status="active",
        config={"api_key": "must-not-leak"},
        consecutive_failure_count=0,
        total_records_harvested=0,
        total_active_records=0,
        total_deleted_records=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    payload = SourceRead.model_validate(source).model_dump()
    assert "config" not in payload
    assert "connection_config" not in payload
    assert "must-not-leak" not in str(payload)


def test_secret_fields_are_not_persisted_in_connection_config() -> None:
    result = _sanitize_for_storage(
        {"api_key": "secret", "password": "secret", "header_name": "X-ResearchHub"}
    )
    assert result == {"header_name": "X-ResearchHub"}


def test_file_source_connection_test_is_explicitly_deferred() -> None:
    result = asyncio.run(
        run_connection_test("json_import", "json", "JSON import", None, "oai_dc", None)
    )
    assert result["success"] is True
    assert "not implemented" in result["warnings"][0]


def test_oai_connection_test_requires_endpoint() -> None:
    with pytest.raises(ValueError, match="endpoint"):
        asyncio.run(run_connection_test("oai_pmh", "missing", "Missing", None, "oai_dc", None))
