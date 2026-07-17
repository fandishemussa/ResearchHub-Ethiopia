"""Explicit extension points for future non-OAI provider connectors."""

from collections.abc import AsyncIterator, Iterable
from typing import Any

from researchhub_harvester.connectors.base import (
    MetadataConnector,
    NormalizedPublication,
    RawRecord,
    ValidationResult,
)


class NotImplementedProviderConnector(MetadataConnector):
    """Base class for registered provider connectors planned after OAI-PMH."""

    provider_name = "provider"

    async def identify(self) -> dict[str, Any]:
        """Return provider status and implementation state."""

        return {"provider": self.provider_name, "implemented": False}

    async def collect(self, **kwargs: Any) -> AsyncIterator[RawRecord]:
        """Stop collection until this provider is implemented."""

        if False:
            yield  # pragma: no cover - keeps this method an async generator.
        msg = f"{self.provider_name} connector is registered but not implemented in v0.1"
        raise NotImplementedError(msg)

    def normalize(self, raw_record: RawRecord) -> NormalizedPublication:
        """Normalize provider records once implemented."""

        msg = f"{self.provider_name} normalization is not implemented in v0.1"
        raise NotImplementedError(msg)

    def validate(self, publication: NormalizedPublication) -> ValidationResult:
        """Validation is inherited by concrete provider implementations later."""

        return ValidationResult(valid=True, issues=[])

    def export(self, publications: Iterable[NormalizedPublication]) -> list[dict[str, Any]]:
        """Export provider records once implemented."""

        return [publication.asdict() for publication in publications]


class OpenAlexConnector(NotImplementedProviderConnector):
    """OpenAlex extension point."""

    provider_name = "OpenAlex"


class CrossrefConnector(NotImplementedProviderConnector):
    """Crossref extension point."""

    provider_name = "Crossref"


class DataCiteConnector(NotImplementedProviderConnector):
    """DataCite extension point."""

    provider_name = "DataCite"


class ORCIDConnector(NotImplementedProviderConnector):
    """ORCID extension point."""

    provider_name = "ORCID"
