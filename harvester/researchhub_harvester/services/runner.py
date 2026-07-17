"""Connector runner that normalizes, validates, deduplicates, and exports records."""

from collections.abc import Awaitable, Callable
from typing import Any

from researchhub_harvester.connectors.base import MetadataConnector, NormalizedPublication
from researchhub_harvester.services.deduplication import PublicationDeduplicator

PublicationSink = Callable[[NormalizedPublication], Awaitable[None]]


class HarvestRunner:
    """Orchestrate a connector harvest without coupling it to FastAPI or SQLAlchemy."""

    def __init__(self, connector: MetadataConnector, sink: PublicationSink) -> None:
        self.connector = connector
        self.sink = sink
        self.deduplicator = PublicationDeduplicator()

    async def run(self, **collect_kwargs: Any) -> dict[str, int]:
        """Collect records and export valid, non-duplicate publications to the sink."""

        stats = {"seen": 0, "exported": 0, "duplicates": 0, "invalid": 0}
        async for raw_record in self.connector.collect(**collect_kwargs):
            stats["seen"] += 1
            publication = self.connector.normalize(raw_record)
            validation = self.connector.validate(publication)
            if not validation.valid:
                stats["invalid"] += 1
                continue
            if self.deduplicator.seen(publication):
                stats["duplicates"] += 1
                continue
            await self.sink(publication)
            stats["exported"] += 1
        return stats
