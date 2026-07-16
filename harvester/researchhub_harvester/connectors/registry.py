"""Connector registry for configuration-driven source onboarding."""

from collections.abc import Callable

from researchhub_harvester.connectors.base import ConnectorConfig, MetadataConnector
from researchhub_harvester.connectors.dspace_discovery import DSpaceDiscoveryConnector
from researchhub_harvester.connectors.oai_pmh import OAIPMHConnector
from researchhub_harvester.connectors.placeholders import (
    CrossrefConnector,
    DataCiteConnector,
    OpenAlexConnector,
    ORCIDConnector,
)

ConnectorFactory = Callable[[ConnectorConfig], MetadataConnector]


CONNECTORS: dict[str, type[MetadataConnector]] = {
    "oai-pmh": OAIPMHConnector,
    "dspace-discovery": DSpaceDiscoveryConnector,
    "dspace_discovery": DSpaceDiscoveryConnector,
    "openalex": OpenAlexConnector,
    "crossref": CrossrefConnector,
    "datacite": DataCiteConnector,
    "orcid": ORCIDConnector,
}


def create_connector(connector_type: str, config: ConnectorConfig) -> MetadataConnector:
    """Create a connector instance from a stored connector type."""

    try:
        connector_cls = CONNECTORS[connector_type.casefold()]
    except KeyError as exc:
        msg = f"Unsupported connector type: {connector_type}"
        raise ValueError(msg) from exc
    return connector_cls(config)
