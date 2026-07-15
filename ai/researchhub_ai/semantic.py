"""Initial AI module for semantic search, enrichment, similarity, and recommendations."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SemanticDocument:
    """Small document object used by semantic search and similarity services."""

    id: str
    title: str
    abstract: str | None = None
    keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Return normalized text used by embedding or fallback lexical matching."""

        return " ".join([self.title, self.abstract or "", " ".join(self.keywords)]).strip()


class SemanticPublicationService:
    """AI facade with lazy model loading and deterministic fallback behavior."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: Any | None = None

    def semantic_search(
        self, query: str, documents: Iterable[SemanticDocument], limit: int = 10
    ) -> list[tuple[SemanticDocument, float]]:
        """Rank documents semantically when embeddings exist, otherwise lexical cosine."""

        docs = list(documents)
        if not docs:
            return []
        if self._can_load_model():
            return self._embedding_search(query, docs, limit)
        return self._lexical_search(query, docs, limit)

    def generate_keywords(self, title: str, abstract: str | None = None, limit: int = 8) -> list[str]:
        """Generate first-pass keywords from title and abstract without an LLM dependency."""

        text = f"{title} {abstract or ''}".casefold()
        tokens = [
            token
            for token in re.findall(r"[a-z][a-z-]{3,}", text)
            if token not in _STOPWORDS
        ]
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        return [term for term, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]

    def enrich_metadata(self, document: SemanticDocument) -> dict[str, Any]:
        """Return deterministic metadata enrichment suggestions."""

        return {
            "suggested_keywords": self.generate_keywords(document.title, document.abstract),
            "has_abstract": bool(document.abstract),
            "text_length": len(document.text),
        }

    def similar_publications(
        self, target: SemanticDocument, candidates: Iterable[SemanticDocument], limit: int = 10
    ) -> list[tuple[SemanticDocument, float]]:
        """Return publications similar to the target document."""

        return self.semantic_search(target.text, candidates, limit=limit)

    def recommendations(
        self, interests: list[str], candidates: Iterable[SemanticDocument], limit: int = 10
    ) -> list[tuple[SemanticDocument, float]]:
        """Recommend publications from researcher interests."""

        return self.semantic_search(" ".join(interests), candidates, limit=limit)

    def _can_load_model(self) -> bool:
        """Return True when sentence-transformers can be imported and loaded."""

        if self._model is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            return True
        except Exception:
            return False

    def _embedding_search(
        self, query: str, documents: list[SemanticDocument], limit: int
    ) -> list[tuple[SemanticDocument, float]]:
        """Rank documents with sentence-transformer embeddings."""

        texts = [query, *[document.text for document in documents]]
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        query_embedding = embeddings[0]
        scored = [
            (document, float(query_embedding @ embedding))
            for document, embedding in zip(documents, embeddings[1:], strict=True)
        ]
        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    def _lexical_search(
        self, query: str, documents: list[SemanticDocument], limit: int
    ) -> list[tuple[SemanticDocument, float]]:
        """Rank documents with deterministic token cosine similarity."""

        query_vector = _term_vector(query)
        scored = [
            (document, _cosine(query_vector, _term_vector(document.text))) for document in documents
        ]
        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]


def _term_vector(text: str) -> dict[str, float]:
    """Create a sparse term-frequency vector."""

    vector: dict[str, float] = {}
    for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.casefold()):
        if token in _STOPWORDS:
            continue
        vector[token] = vector.get(token, 0.0) + 1.0
    return vector


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    """Return cosine similarity between sparse vectors."""

    if not left or not right:
        return 0.0
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


_STOPWORDS = {
    "about",
    "after",
    "among",
    "analysis",
    "based",
    "between",
    "from",
    "into",
    "research",
    "study",
    "that",
    "their",
    "this",
    "using",
    "with",
}

