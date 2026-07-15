"""Small domain value helpers shared by API and harvester code."""

import re
from dataclasses import dataclass
from datetime import date

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DateRange:
    """Inclusive date range used by incremental harvesting and analytics."""

    start: date | None = None
    end: date | None = None

    def validate(self) -> None:
        """Raise when the date range is internally inconsistent."""

        if self.start and self.end and self.start > self.end:
            msg = "start date must be before or equal to end date"
            raise ValueError(msg)


def normalize_doi(value: str | None) -> str | None:
    """Extract and canonicalize a DOI from free text."""

    if not value:
        return None
    match = DOI_RE.search(value.strip())
    return match.group(0).lower() if match else None


def normalize_orcid(value: str | None) -> str | None:
    """Extract and canonicalize an ORCID identifier from free text."""

    if not value:
        return None
    match = ORCID_RE.search(value.strip())
    return match.group(0).upper() if match else None

