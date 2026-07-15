"""Cached CPU-first SentenceTransformer publication embeddings."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from functools import lru_cache
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


def normalize_whitespace(value: str) -> str:
    """Collapse repeated whitespace deterministically."""

    return re.sub(r"\s+", " ", value).strip()


def normalize_subjects(subjects: object) -> list[str]:
    """Return unique, non-empty subject strings while preserving order."""

    if not isinstance(subjects, (list, tuple)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for subject in subjects:
        if not isinstance(subject, str):
            continue
        normalized = normalize_whitespace(subject)
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def build_publication_text(title: str, abstract: str | None, subjects: object) -> str:
    """Build deterministic model input; tokenizer-level truncation uses model defaults."""

    normalized_title = normalize_whitespace(title) if isinstance(title, str) else ""
    if not normalized_title:
        raise ValueError("Publication title is required for embedding")
    normalized_abstract = normalize_whitespace(abstract) if isinstance(abstract, str) else ""
    normalized_subjects = normalize_subjects(subjects)
    return "\n".join(
        (
            f"Title: {normalized_title}",
            f"Abstract: {normalized_abstract}",
            f"Subjects: {'; '.join(normalized_subjects)}",
        )
    )


class Encoder(Protocol):
    """Interface shared by production encoders and test doubles."""

    def encode_documents(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]: ...
    def encode_query(self, query: str) -> list[float]: ...
    def get_embedding_dimension(self) -> int: ...
    def get_model_name(self) -> str: ...


class SentenceTransformerEmbeddingService:
    """Lazy SentenceTransformer wrapper with normalized 384-dimensional output."""

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            LOGGER.info("Loading embedding model %s on %s", self.model_name, self.device)
            self._model = SentenceTransformer(self.model_name, device=self.device)
        get_dimension = getattr(
            self._model,
            "get_embedding_dimension",
            self._model.get_sentence_embedding_dimension,
        )
        dimension = int(get_dimension())
        if dimension != EMBEDDING_DIMENSION:
            self._model = None
            raise ValueError(
                f"Embedding model dimension {dimension} does not match required "
                f"dimension {EMBEDDING_DIMENSION}"
            )
        return self._model

    def encode_documents(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        if batch_size < 1:
            raise ValueError("batch_size must be greater than zero")
        if not texts:
            return []
        model = self._load_model()
        from torch import inference_mode

        with inference_mode():
            embeddings = model.encode(
                list(texts),
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return embeddings.tolist()

    def encode_query(self, query: str) -> list[float]:
        normalized = normalize_whitespace(query)
        if not normalized:
            raise ValueError("Semantic search query must not be blank")
        return self.encode_documents([normalized], batch_size=1)[0]

    def get_embedding_dimension(self) -> int:
        model = self._load_model()
        get_dimension = getattr(
            model,
            "get_embedding_dimension",
            model.get_sentence_embedding_dimension,
        )
        return int(get_dimension())

    def get_model_name(self) -> str:
        return self.model_name


@lru_cache(maxsize=8)
def get_embedding_service(
        model_name: str = DEFAULT_MODEL,
        device: str = "cpu",
) -> SentenceTransformerEmbeddingService:
    """Return one lazy encoder per model/device pair."""

    return SentenceTransformerEmbeddingService(model_name=model_name, device=device)
