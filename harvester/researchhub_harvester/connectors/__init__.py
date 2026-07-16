"""Connector implementations and registry helpers."""

from researchhub_harvester.connectors.base import MetadataConnector
from researchhub_harvester.connectors.dspace_discovery import DSpaceDiscoveryConnector
from researchhub_harvester.connectors.oai_pmh import OAIPMHConnector

__all__ = ["DSpaceDiscoveryConnector", "MetadataConnector", "OAIPMHConnector"]
