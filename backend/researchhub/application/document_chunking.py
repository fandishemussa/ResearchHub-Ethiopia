from __future__ import annotations

from dataclasses import dataclass

from researchhub.application.document_extraction import ExtractedPage


@dataclass(slots=True)
class TextChunk:
    chunk_index: int
    page_start: int
    page_end: int
    content: str


def chunk_pages(
    pages: list[ExtractedPage],
    *,
    chunk_size: int = 3500,
    overlap: int = 500,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size")

    chunks: list[TextChunk] = []
    chunk_index = 0

    for page in pages:
        text = page.text.strip()

        if not text:
            continue

        start = 0

        while start < len(text):
            end = min(
                start + chunk_size,
                len(text),
            )

            # Prefer ending at a paragraph or sentence boundary.
            if end < len(text):
                paragraph_break = text.rfind(
                    "\n\n",
                    start,
                    end,
                )

                sentence_break = text.rfind(
                    ". ",
                    start,
                    end,
                )

                best_break = max(
                    paragraph_break,
                    sentence_break,
                )

                if best_break > start + chunk_size // 2:
                    end = best_break + 1

            content = text[start:end].strip()

            if content:
                chunks.append(
                    TextChunk(
                        chunk_index=chunk_index,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        content=content,
                    )
                )

                chunk_index += 1

            if end >= len(text):
                break

            start = max(
                end - overlap,
                start + 1,
            )

    return chunks
