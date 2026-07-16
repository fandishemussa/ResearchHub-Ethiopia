"""Focused safety and serialization coverage for indexed document APIs."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from researchhub.application.documents import ResearchDocumentService, _public_url
from researchhub.domain.schemas import ResearchDocumentRead
from sqlalchemy.ext.asyncio import AsyncSession


class FakeSession:
    def __init__(self, item: object | None) -> None:
        self.item = item

    async def get(self, _model: object, _document_id: object) -> object | None:
        return self.item


def test_document_schema_never_serializes_local_path() -> None:
    document = ResearchDocumentRead.model_validate(
        {
            "id": uuid4(),
            "publication_id": None,
            "source": "bdu",
            "title": "Indexed paper",
            "extraction_status": "indexed",
            "metadata": {"document_type": "thesis"},
            "local_path": "C:/secret/research.pdf",
        }
    )

    payload = document.model_dump(mode="json")
    assert "local_path" not in payload
    assert payload["metadata"] == {"document_type": "thesis"}


@pytest.mark.asyncio
async def test_content_path_requires_registered_existing_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    session = cast(AsyncSession, FakeSession(SimpleNamespace(local_path=str(pdf))))
    service = ResearchDocumentService(session)

    assert await service.content_path(uuid4()) == pdf.resolve()


@pytest.mark.asyncio
async def test_content_path_rejects_non_pdf_and_missing_record(tmp_path: Path) -> None:
    text_file = tmp_path / "paper.txt"
    text_file.write_text("not a PDF", encoding="utf-8")
    non_pdf = ResearchDocumentService(
        cast(AsyncSession, FakeSession(SimpleNamespace(local_path=str(text_file))))
    )
    missing = ResearchDocumentService(cast(AsyncSession, FakeSession(None)))

    with pytest.raises(LookupError, match="preview is unavailable"):
        await non_pdf.content_path(uuid4())
    with pytest.raises(LookupError, match="not found"):
        await missing.content_path(uuid4())


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "https://repository.example/paper.pdf",
            "https://repository.example/paper.pdf",
        ),
        ("http://repository.example/item/1", "http://repository.example/item/1"),
        ("file:///app/data/private.pdf", None),
        ("C:/data/private.pdf", None),
        ("javascript:alert(1)", None),
        (None, None),
    ],
)
def test_public_document_urls_are_http_only(
    value: str | None, expected: str | None
) -> None:
    assert _public_url(value) == expected
