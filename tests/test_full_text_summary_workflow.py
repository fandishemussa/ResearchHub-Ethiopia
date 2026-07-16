from types import SimpleNamespace

import pytest
from researchhub.application.full_text_summary import (
    NOT_FOUND,
    summarize_document_chunks,
)
from researchhub.application.publication_documents import DocumentSourceProbe
from researchhub.core.config import Settings


def chunk(index: int, page: int, content: str) -> SimpleNamespace:
    return SimpleNamespace(chunk_index=index, page_start=page, page_end=page, content=content)


def test_full_text_summary_is_page_aware_and_structured() -> None:
    result = summarize_document_chunks(
        [
            chunk(0, 1, "The purpose of this study was to assess women's economic empowerment."),
            chunk(1, 12, "The methodology used a mixed-method design with 240 respondents."),
            chunk(2, 40, "The findings showed that access to credit improved participation."),
            chunk(3, 45, "The study recommends expanding affordable financial services."),
        ]
    )

    assert "Objectives" in result.text
    assert "Methodology" in result.text
    assert "[p. 12]" in result.text
    assert result.pages_used == [1, 12, 40, 45]
    assert result.chunk_count == 4


def test_full_text_summary_deduplicates_chunks_and_marks_missing_evidence() -> None:
    repeated = "The methodology used interviews with participants from Wolkite Town."
    result = summarize_document_chunks([chunk(0, 3, repeated), chunk(1, 3, repeated)])

    assert result.chunk_count == 1
    assert NOT_FOUND in result.text


@pytest.mark.asyncio
async def test_document_probe_rejects_unsupported_protocol() -> None:
    probe = DocumentSourceProbe(Settings())
    result = await probe.probe("file:///app/data/private.pdf")

    assert result.reachable is False
    assert result.error_code == "unsupported_protocol"


@pytest.mark.asyncio
async def test_document_probe_rejects_credentials_in_url() -> None:
    probe = DocumentSourceProbe(Settings())
    result = await probe.probe("https://user:secret@example.org/paper.pdf")

    assert result.reachable is False
    assert result.error_code == "credentials_in_url"
