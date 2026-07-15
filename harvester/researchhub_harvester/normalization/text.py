"""Text, identifier, date, and URL normalization helpers."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse, urlunparse

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", re.IGNORECASE)
ISSN_RE = re.compile(r"\b\d{4}-\d{3}[\dX]\b", re.IGNORECASE)

LANGUAGE_MAP = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "am": "am",
    "amh": "am",
    "amharic": "am",
    "om": "om",
    "orm": "om",
    "oromo": "om",
    "aa": "aa",
    "afar": "aa",
    "ti": "ti",
    "tir": "ti",
    "tigrinya": "ti",
}


def normalize_whitespace(value: str | None) -> str | None:
    """Collapse whitespace and strip empty strings to None."""

    if value is None:
        return None
    normalized = " ".join(value.replace("\u00a0", " ").split())
    return normalized or None


def normalize_title(value: str | None) -> str | None:
    """Normalize publication title spacing and trailing punctuation."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    return normalized.rstrip(" /:")


def normalize_author_name(value: str | None) -> str | None:
    """Normalize author display names while preserving normal capitalization."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    if "," in normalized:
        last, first = [part.strip() for part in normalized.split(",", 1)]
        normalized = f"{first} {last}".strip()
    return normalized


def normalize_doi(value: str | None) -> str | None:
    """Extract and canonicalize DOI values from URLs or provider text."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    match = DOI_RE.search(normalized)
    return match.group(0).lower() if match else None


def normalize_orcid(value: str | None) -> str | None:
    """Extract an ORCID and validate its checksum when present."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    match = ORCID_RE.search(normalized)
    if not match:
        return None
    orcid = match.group(0).upper()
    return orcid if _valid_orcid_checksum(orcid) else None


def _valid_orcid_checksum(orcid: str) -> bool:
    """Return True when an ORCID check digit is valid."""

    total = 0
    digits = orcid.replace("-", "")
    for char in digits[:-1]:
        total = (total + int(char)) * 2
    remainder = total % 11
    result = (12 - remainder) % 11
    check_digit = "X" if result == 10 else str(result)
    return check_digit == digits[-1]


def normalize_issn(value: str | None) -> str | None:
    """Extract an ISSN from provider metadata."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    match = ISSN_RE.search(normalized)
    return match.group(0).upper() if match else None


def normalize_language(value: str | None) -> str | None:
    """Normalize language names and ISO variants to compact language codes."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    return LANGUAGE_MAP.get(normalized.casefold(), normalized.casefold())


def normalize_url(value: str | None) -> str | None:
    """Normalize provider URLs while preserving path and query."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    if not parsed.scheme or not parsed.netloc:
        return None
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            "",
            parsed.query,
            "",
        )
    )


def parse_date(value: str | None) -> date | None:
    """Parse common repository date formats without external dependencies."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    for pattern in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            if pattern == "%Y":
                return date(int(normalized[:4]), 1, 1)
            if pattern == "%Y-%m" and re.fullmatch(r"\d{4}-\d{2}", normalized):
                return date(int(normalized[:4]), int(normalized[5:7]), 1)
            if pattern == "%Y-%m-%d" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
                return date.fromisoformat(normalized)
        except ValueError:
            return None
    year = parse_year(normalized)
    return date(year, 1, 1) if year else None


def parse_year(value: str | None) -> int | None:
    """Extract a plausible publication year from free text."""

    normalized = normalize_whitespace(value)
    if normalized is None:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", normalized)
    return int(match.group(0)) if match else None


def split_terms(values: list[str]) -> list[str]:
    """Split semicolon/comma-separated keyword fields into unique ordered terms."""

    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        for part in re.split(r"[;,]", value):
            term = normalize_whitespace(part)
            if term and term.casefold() not in seen:
                seen.add(term.casefold())
                terms.append(term)
    return terms

