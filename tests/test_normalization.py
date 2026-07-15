"""Tests for metadata normalization helpers."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harvester"))

from researchhub_harvester.normalization.text import (  # noqa: E402
    normalize_author_name,
    normalize_doi,
    normalize_language,
    normalize_orcid,
    normalize_title,
    parse_date,
    split_terms,
)


class NormalizationTests(unittest.TestCase):
    """Verify deterministic metadata normalization."""

    def test_normalize_title_and_author(self) -> None:
        """Whitespace and comma-separated names are normalized."""

        self.assertEqual(normalize_title("  Climate   adaptation:  "), "Climate adaptation")
        self.assertEqual(normalize_author_name("Lemma, Tesfaye"), "Tesfaye Lemma")

    def test_identifier_normalization(self) -> None:
        """DOI and ORCID identifiers are extracted and canonicalized."""

        self.assertEqual(
            normalize_doi("https://doi.org/10.1234/ABC.Def"),
            "10.1234/abc.def",
        )
        self.assertEqual(
            normalize_orcid("https://orcid.org/0000-0002-1825-0097"),
            "0000-0002-1825-0097",
        )

    def test_dates_languages_and_terms(self) -> None:
        """Repository date, language, and keyword variants normalize cleanly."""

        self.assertEqual(parse_date("2023-05").isoformat(), "2023-05-01")
        self.assertEqual(normalize_language("Amharic"), "am")
        self.assertEqual(split_terms(["soil; water, climate", "soil"]), ["soil", "water", "climate"])


if __name__ == "__main__":
    unittest.main()

