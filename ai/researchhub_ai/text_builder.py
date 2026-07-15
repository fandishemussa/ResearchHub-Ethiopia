"""Canonical normalized publication text for every AI operation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from html import unescape
from typing import Any

TAG_PATTERN = re.compile(r"<[^>]+>")
SPACE_PATTERN = re.compile(r"[ \t]+")
BREAK_PATTERN = re.compile(r"\r\n?|\n{3,}")


@dataclass(frozen=True)
class BuiltPublicationText:
    text: str
    content_hash: str
    source_fields: tuple[str, ...]


class PublicationTextBuilder:
    def __init__(self, max_characters: int = 30_000) -> None:
        if max_characters < 500:
            raise ValueError("max_characters must be at least 500")
        self.max_characters = max_characters

    def build_embedding_text(self, publication: Any) -> BuiltPublicationText:
        return self._build(publication, include_abstract=True)

    def build_summary_text(self, publication: Any) -> BuiltPublicationText:
        return self._build(publication, include_abstract=True)

    def build_keyword_text(self, publication: Any) -> BuiltPublicationText:
        return self._build(publication, include_abstract=True, repeat_title=True)

    def build_duplicate_text(self, publication: Any) -> BuiltPublicationText:
        return self._build(publication, include_abstract=True)

    def build_chatbot_document(self, publication: Any) -> BuiltPublicationText:
        return self._build(publication, include_abstract=True)

    def _build(self, publication: Any, *, include_abstract: bool, repeat_title: bool = False) -> BuiltPublicationText:
        if getattr(publication, "is_deleted", False):
            raise ValueError("Deleted publications cannot be used for AI operations")
        authors = [link.author.full_name for link in getattr(publication, "authors", []) if getattr(link, "author", None)]
        keywords = [link.keyword.term for link in getattr(publication, "keywords", []) if getattr(link, "keyword", None)]
        journal = getattr(getattr(publication, "journal", None), "name", None)
        values: list[tuple[str, Any]] = [
            ("Title", getattr(publication, "title", None)),
            ("Abstract", getattr(publication, "abstract", None) if include_abstract else None),
            ("Keywords", keywords),
            ("Subjects", getattr(publication, "subjects", [])),
            ("Authors", authors),
            ("Journal", journal),
            ("Publication Year", getattr(publication, "publication_year", None)),
        ]
        seen: set[str] = set()
        sections: list[str] = []
        fields: list[str] = []
        for label, raw in values:
            items = raw if isinstance(raw, list) else [raw]
            cleaned = []
            for value in items:
                normalized = clean_ai_text(str(value)) if value is not None else ""
                key = normalized.casefold()
                if normalized and key not in seen:
                    seen.add(key)
                    cleaned.append(normalized)
            if cleaned:
                content = "; ".join(cleaned)
                if repeat_title and label == "Title":
                    content = f"{content}\n{content}"
                sections.append(f"{label}:\n{content}")
                fields.append(label.casefold().replace(" ", "_"))
        text = "\n\n".join(sections)[: self.max_characters].rstrip()
        if not text:
            raise ValueError("Publication contains no usable AI text")
        return BuiltPublicationText(text=text, content_hash=sha256(text.encode("utf-8")).hexdigest(), source_fields=tuple(fields))


def clean_ai_text(value: str) -> str:
    value = unescape(TAG_PATTERN.sub(" ", value))
    value = BREAK_PATTERN.sub("\n", value)
    return SPACE_PATTERN.sub(" ", value).strip()
