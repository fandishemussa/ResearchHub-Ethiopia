"""Page-aware extractive full-text summarization without unsupported claims."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from researchhub.infrastructure.persistence.models import DocumentChunk

NOT_FOUND = "Not clearly identified in the indexed document."
SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "Study overview": ("abstract", "overview", "this study", "this research"),
    "Research problem": ("problem", "background", "challenge", "gap"),
    "Objectives": ("objective", "aim", "purpose"),
    "Methodology": ("method", "design", "sample", "data collection", "analysis"),
    "Study area or population": ("study area", "population", "participants", "respondents"),
    "Main findings": ("result", "finding", "revealed", "showed", "indicated"),
    "Conclusions": ("conclusion", "concluded"),
    "Recommendations": ("recommend", "suggest"),
    "Limitations": ("limitation", "constraint"),
}


@dataclass(slots=True)
class FullTextSummaryResult:
    text: str
    pages_used: list[int]
    chunk_count: int
    content_hash: str


def _sentences(value: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", value)
        if 35 <= len(part.strip()) <= 600
    ]


def _normalized(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


def summarize_document_chunks(
    chunks: list[DocumentChunk], *, max_section_sentences: int = 2
) -> FullTextSummaryResult:
    """Build a bounded structured summary from ordered, de-duplicated chunks."""

    unique: list[DocumentChunk] = []
    seen_chunks: set[str] = set()
    for chunk in sorted(chunks, key=lambda item: (item.page_start or 0, item.chunk_index)):
        normalized = _normalized(chunk.content)
        digest = sha256(normalized.encode()).hexdigest()
        if not normalized or digest in seen_chunks:
            continue
        seen_chunks.add(digest)
        unique.append(chunk)

    candidates: list[tuple[str, int | None]] = []
    seen_sentences: set[str] = set()
    for chunk in unique:
        for sentence in _sentences(chunk.content):
            normalized = _normalized(sentence)
            if len(normalized.split()) < 7 or normalized in seen_sentences:
                continue
            seen_sentences.add(normalized)
            candidates.append((sentence, chunk.page_start))

    output: list[str] = []
    pages: set[int] = set()
    for heading, terms in SECTION_PATTERNS.items():
        ranked: list[tuple[int, int, str, int | None]] = []
        for position, (sentence, page) in enumerate(candidates):
            lowered = sentence.casefold()
            score = sum(term in lowered for term in terms)
            if score:
                ranked.append((-score, position, sentence, page))
        selected = sorted(ranked)[:max_section_sentences]
        if not selected:
            output.append(f"{heading}\n{NOT_FOUND}")
            continue
        statements: list[str] = []
        for _, _, sentence, page in selected:
            reference = f" [p. {page}]" if page else ""
            statements.append(sentence.rstrip() + reference)
            if page:
                pages.add(page)
        output.append(f"{heading}\n{' '.join(statements)}")

    evidence = ", ".join(str(page) for page in sorted(pages)) or NOT_FOUND
    output.append(f"Key evidence pages\n{evidence}")
    content_hash = sha256(
        "\n".join(f"{chunk.chunk_index}:{chunk.content}" for chunk in unique).encode()
    ).hexdigest()
    return FullTextSummaryResult(
        text="\n\n".join(output),
        pages_used=sorted(pages),
        chunk_count=len(unique),
        content_hash=content_hash,
    )
