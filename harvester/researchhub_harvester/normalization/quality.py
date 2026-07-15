"""Metadata quality scoring for normalized publications."""

from collections.abc import Mapping
from typing import Any

REQUIRED_FIELDS = ("title", "authors", "publication_year", "source", "source_type")
HIGH_VALUE_FIELDS = ("doi", "abstract", "keywords", "language", "article_url")


def quality_score(record: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    """Return a 0-100 score, missing fields, and warnings for metadata quality."""

    missing = [field for field in REQUIRED_FIELDS if not record.get(field)]
    warnings: list[str] = []
    score = 100.0
    score -= len(missing) * 14.0
    for field in HIGH_VALUE_FIELDS:
        if not record.get(field):
            score -= 5.0
            warnings.append(f"Missing {field}")
    if record.get("is_deleted"):
        warnings.append("Record is marked deleted by source")
    return max(score, 0.0), missing, warnings

