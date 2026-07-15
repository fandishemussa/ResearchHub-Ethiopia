"""Tests for AAU ETD JSON import normalization."""

from datetime import date

import pytest

from scripts.import_aau_json import parse_date


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024", date(2024, 1, 1)),
        ("2024-06", date(2024, 6, 1)),
        ("2024-06-15", date(2024, 6, 15)),
        ("3/31/2015", date(2015, 3, 31)),
        ("January, 2025", date(2025, 1, 1)),
        ("2024-06-15T10:30:00Z", date(2024, 6, 15)),
    ],
)
def test_parse_supported_aau_dates(raw: str, expected: date) -> None:
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "2-10", "201-06", "2025-15"])
def test_parse_invalid_aau_dates_as_missing(raw: object) -> None:
    assert parse_date(raw) is None
