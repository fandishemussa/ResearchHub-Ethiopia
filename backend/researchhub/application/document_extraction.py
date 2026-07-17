from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz
from docx import Document


@dataclass(slots=True)
class ExtractedPage:
    page_number: int
    text: str


def clean_extracted_text(text: str) -> str:
    text = text.replace("\x00", " ")

    # Join words split across PDF line breaks.
    text = re.sub(
        r"(?<=\w)-\s*\n\s*(?=\w)",
        "",
        text,
    )

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_pdf(path: Path) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []

    with fitz.open(str(path)) as document:
        for page_index, page in enumerate(document):
            text = page.get_text(
                "text",
                sort=True,
            )

            cleaned = clean_extracted_text(text)

            if cleaned:
                pages.append(
                    ExtractedPage(
                        page_number=page_index + 1,
                        text=cleaned,
                    )
                )

    return pages


def extract_docx(path: Path) -> list[ExtractedPage]:
    document = Document(str(path))

    paragraphs = [
        paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()
    ]

    text = clean_extracted_text("\n\n".join(paragraphs))

    return (
        [
            ExtractedPage(
                page_number=1,
                text=text,
            )
        ]
        if text
        else []
    )


def extract_document(path: Path) -> list[ExtractedPage]:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf(path)

    if suffix == ".docx":
        return extract_docx(path)

    raise ValueError(f"Unsupported document format: {suffix}")
