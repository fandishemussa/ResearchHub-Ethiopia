"""JSON configuration loading for harvest connector execution.

The harvesting engine can be driven entirely from JSON so universities and
repositories can be onboarded by configuration rather than code changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from researchhub_harvester.connectors.base import ConnectorConfig


@dataclass(frozen=True, slots=True)
class HarvestConnectorDefinition:
    """Configuration for one connector execution target."""

    code: str
    name: str
    connector_type: str
    base_url: str
    source_type: str
    enabled: bool = True
    metadata_prefix: str = "oai_dc"
    set_spec: str | None = None
    from_date: date | None = None
    until_date: date | None = None
    schedule: str | None = None
    connector_id: UUID | None = None
    university_id: UUID | None = None
    repository_id: UUID | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    max_retries: int = 4
    backoff_factor: float = 0.5
    max_backoff_seconds: float = 30.0
    rate_limit_per_second: float = 2.0
    pool_connections: int = 10
    pool_maxsize: int = 20
    user_agent: str = "ResearchHubEthiopia/0.1"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_connector_config(self) -> ConnectorConfig:
        """Convert JSON connector settings to a connector runtime config."""

        return ConnectorConfig(
            code=self.code,
            name=self.name,
            base_url=self.base_url,
            source_type=self.source_type,
            metadata_prefix=self.metadata_prefix,
            set_spec=self.set_spec,
            from_date=self.from_date,
            until_date=self.until_date,
            headers=self.headers,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            backoff_factor=self.backoff_factor,
            max_backoff_seconds=self.max_backoff_seconds,
            rate_limit_per_second=self.rate_limit_per_second,
            pool_connections=self.pool_connections,
            pool_maxsize=self.pool_maxsize,
            user_agent=self.user_agent,
            extra={
                **self.extra,
                "connector_type": self.connector_type,
                "connector_id": str(self.connector_id) if self.connector_id else None,
                "university_id": str(self.university_id) if self.university_id else None,
                "repository_id": str(self.repository_id) if self.repository_id else None,
                "schedule": self.schedule,
            },
        )

    def collect_kwargs(self) -> dict[str, Any]:
        """Return collection parameters passed into connector collection."""

        return {
            "metadata_prefix": self.metadata_prefix,
            "from_date": self.from_date,
            "until_date": self.until_date,
            "set_spec": self.set_spec,
        }


@dataclass(frozen=True, slots=True)
class HarvestEngineConfig:
    """Top-level engine configuration loaded from JSON."""

    connectors: list[HarvestConnectorDefinition]
    max_concurrent_connectors: int = 3
    retry_failed_jobs: bool = True
    job_max_attempts: int = 3

    @property
    def enabled_connectors(self) -> list[HarvestConnectorDefinition]:
        """Return connectors enabled for execution."""

        return [connector for connector in self.connectors if connector.enabled]

    def connector_by_code(self, code: str) -> HarvestConnectorDefinition:
        """Return an enabled or disabled connector definition by code."""

        for connector in self.connectors:
            if connector.code == code:
                return connector
        msg = f"Connector not found in harvest config: {code}"
        raise KeyError(msg)


def load_harvest_config(source: str | Path | dict[str, Any]) -> HarvestEngineConfig:
    """Load harvest engine configuration from a JSON file path or dictionary."""

    payload = _read_config_payload(source)
    connectors = [_parse_connector_definition(item) for item in payload.get("connectors", [])]
    return HarvestEngineConfig(
        connectors=connectors,
        max_concurrent_connectors=int(payload.get("max_concurrent_connectors", 3)),
        retry_failed_jobs=bool(payload.get("retry_failed_jobs", True)),
        job_max_attempts=int(payload.get("job_max_attempts", 3)),
    )


def _read_config_payload(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Return a configuration mapping from file path or mapping input."""

    if isinstance(source, dict):
        return source
    path = Path(source)
    with path.open("r", encoding="utf-8") as file:
        payload: object = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("Harvest configuration must be a JSON object")
    return {str(key): value for key, value in payload.items()}


def _parse_connector_definition(payload: dict[str, Any]) -> HarvestConnectorDefinition:
    """Parse one connector definition from JSON-compatible values."""

    return HarvestConnectorDefinition(
        code=str(payload["code"]),
        name=str(payload.get("name", payload["code"])),
        connector_type=str(payload.get("connector_type", payload.get("type", "oai-pmh"))),
        base_url=str(payload["base_url"]),
        source_type=str(payload.get("source_type", payload.get("connector_type", "oai-pmh"))),
        enabled=bool(payload.get("enabled", True)),
        metadata_prefix=str(payload.get("metadata_prefix", "oai_dc")),
        set_spec=payload.get("set_spec"),
        from_date=_parse_date(payload.get("from_date") or payload.get("from")),
        until_date=_parse_date(payload.get("until_date") or payload.get("until")),
        schedule=payload.get("schedule"),
        connector_id=_parse_uuid(payload.get("connector_id")),
        university_id=_parse_uuid(payload.get("university_id")),
        repository_id=_parse_uuid(payload.get("repository_id")),
        headers=dict(payload.get("headers", {})),
        timeout_seconds=int(payload.get("timeout_seconds", 30)),
        max_retries=int(payload.get("max_retries", 4)),
        backoff_factor=float(payload.get("backoff_factor", 0.5)),
        max_backoff_seconds=float(payload.get("max_backoff_seconds", 30.0)),
        rate_limit_per_second=float(payload.get("rate_limit_per_second", 2.0)),
        pool_connections=int(payload.get("pool_connections", 10)),
        pool_maxsize=int(payload.get("pool_maxsize", 20)),
        user_agent=str(payload.get("user_agent", "ResearchHubEthiopia/0.1")),
        extra=dict(payload.get("extra", {})),
    )


def _parse_date(value: Any) -> date | None:
    """Parse an optional ISO date string."""

    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_uuid(value: Any) -> UUID | None:
    """Parse an optional UUID string."""

    if value in (None, ""):
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
