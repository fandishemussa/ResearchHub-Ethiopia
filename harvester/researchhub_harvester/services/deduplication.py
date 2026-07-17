"""Duplicate detection helpers for normalized connector output."""

from dataclasses import dataclass

from researchhub_harvester.connectors.base import NormalizedPublication


@dataclass(frozen=True, slots=True)
class DuplicateKey:
    """Stable duplicate key that prefers DOI over weaker metadata."""

    kind: str
    value: str


class PublicationDeduplicator:
    """In-memory duplicate detector used before database upsert."""

    def __init__(self) -> None:
        self._seen: set[DuplicateKey] = set()

    def key_for(self, publication: NormalizedPublication) -> DuplicateKey:
        """Return the strongest available duplicate key for a publication."""

        if publication.doi:
            return DuplicateKey("doi", publication.doi.casefold())
        if publication.external_id:
            return DuplicateKey("external_id", f"{publication.source}:{publication.external_id}")
        title = " ".join(publication.title.casefold().split())
        return DuplicateKey("title_year", f"{title}:{publication.publication_year or ''}")

    def seen(self, publication: NormalizedPublication) -> bool:
        """Return True when a publication has already been observed."""

        key = self.key_for(publication)
        if key in self._seen:
            return True
        self._seen.add(key)
        return False
