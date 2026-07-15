"""Tests for deterministic research intelligence features."""

from uuid import uuid4

import pytest
from researchhub.application.research_intelligence import (
    CITATION_STYLES,
    duplicate_score,
    extract_keywords,
    format_citation,
    summarize_text,
)
from researchhub.infrastructure.persistence.models import Author, Publication, PublicationAuthor


def publication(**values: object) -> Publication:
    defaults = {
        "id": uuid4(),
        "title": "Climate adaptation in Ethiopia",
        "source": "test",
        "source_type": "test",
        "publication_year": 2024,
        "doi": "10.1/example",
    }
    defaults.update(values)
    item = Publication(**defaults)
    author = Author(id=uuid4(), full_name="Aster Bekele", normalized_name="aster bekele")
    item.authors = [PublicationAuthor(id=uuid4(), author=author, author_order=1)]
    return item


def test_summary_is_explicitly_abstract_grounded() -> None:
    result = summarize_text(
        "Title",
        "The study assessed soil health. It reports improved outcomes. No other evidence.",
        "short",
    )
    assert result.startswith("Abstract-based summary:")
    assert "improved outcomes" in result


def test_structured_summary_marks_unavailable_limitations() -> None:
    result = summarize_text("Title", "The study assessed soil health.", "structured")
    assert "Limitations: Not stated" in result


def test_keyword_extraction_normalizes_and_scores() -> None:
    result = extract_keywords(
        "Maternal health access",
        "Maternal health access and maternal services",
        ["Public Health"],
        5,
    )
    assert result[0][0] == "maternal"
    assert result[0][1] == 1.0
    assert len({term for term, _ in result}) == len(result)


@pytest.mark.parametrize("style", sorted(CITATION_STYLES))
def test_every_citation_style_handles_normalized_metadata(style: str) -> None:
    result = format_citation(publication(), style)
    assert "Climate adaptation in Ethiopia" in result
    assert "2024" in result
    if style == "bibtex":
        assert result.startswith("@misc{")
    if style == "ris":
        assert result.startswith("TY  - GEN")


def test_doi_match_has_maximum_duplicate_score() -> None:
    first = publication()
    second = publication(title="Entirely different title")
    result = duplicate_score(first, second)
    assert result["doi_match"] is True
    assert result["final_score"] == 1.0


def test_embedding_or_title_similarity_never_merges_records() -> None:
    first = publication(doi=None)
    second = publication(doi=None)
    result = duplicate_score(first, second)
    assert result["final_score"] < 1.0
