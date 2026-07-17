"""Unit tests for publication embedding and semantic-search behavior."""

from __future__ import annotations

import asyncio
import sys
from contextlib import nullcontext
from types import ModuleType
from uuid import uuid4

import pytest
from pydantic import ValidationError
from researchhub.application.embeddings import PublicationEmbeddingProcessor, candidate_statement
from researchhub.application.services import (
    PublicationSimilarityService,
    SemanticSearchService,
    publication_similarity_statement,
    semantic_search_statement,
)
from researchhub.domain.schemas import (
    PublicationSimilarityResponse,
    SemanticSearchResponse,
    SemanticSearchResult,
    SimilarPublicationResult,
)
from researchhub.infrastructure.persistence.models import Publication
from researchhub_ai.embeddings import (
    SentenceTransformerEmbeddingService,
    build_publication_text,
    normalize_subjects,
    normalize_whitespace,
)
from sqlalchemy.dialects import postgresql


class FakeModel:
    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self.calls: list[dict[str, object]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension

    def encode(self, texts: list[str], **kwargs: object):
        self.calls.append({"texts": texts, **kwargs})

        class Vectors:
            def tolist(inner_self) -> list[list[float]]:
                return [[0.0] * self.dimension for _ in texts]

        return Vectors()


class FakeEncoder:
    fail_on_call: int | None = None

    def __init__(self) -> None:
        self.document_calls = 0

    def encode_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        self.document_calls += 1
        if self.fail_on_call == self.document_calls:
            raise RuntimeError("model failure")
        return [[0.0] * 384 for _ in texts]

    def encode_query(self, query: str) -> list[float]:
        return [0.0] * 384

    def get_model_name(self) -> str:
        return "test-model"

    def get_embedding_dimension(self) -> int:
        return 384


class ScalarPage:
    def __init__(self, items: list[Publication]) -> None:
        self.items = items

    def all(self) -> list[Publication]:
        return self.items


class FakeEmbeddingSession:
    def __init__(self, pages: list[list[Publication]]) -> None:
        self.pages = pages
        self.scalar_calls = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def scalar(self, statement: object) -> int:
        return sum(len(page) for page in self.pages)

    async def scalars(self, statement: object) -> ScalarPage:
        page = self.pages[self.scalar_calls] if self.scalar_calls < len(self.pages) else []
        self.scalar_calls += 1
        return ScalarPage(page)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def test_whitespace_and_publication_text_normalization() -> None:
    assert normalize_whitespace("  soil\n  health  ") == "soil health"
    assert build_publication_text(
        " A  title ", None, [" Public  Health ", 3, "public health", "Soil"]
    ) == ("Title: A title\nAbstract: \nSubjects: Public Health; Soil")
    assert normalize_subjects("not-a-list") == []


def test_publication_text_requires_title() -> None:
    with pytest.raises(ValueError, match="title"):
        build_publication_text("  ", "abstract", [])


def test_encoder_uses_normalized_inference_and_validates_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    torch_module = ModuleType("torch")
    torch_module.inference_mode = nullcontext  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    service = SentenceTransformerEmbeddingService("test", "cpu")
    model = FakeModel()
    service._model = model
    vectors = service.encode_documents(["one", "two"], batch_size=2)
    assert len(vectors) == 2
    assert model.calls[0]["normalize_embeddings"] is True
    assert model.calls[0]["show_progress_bar"] is False

    invalid = SentenceTransformerEmbeddingService("invalid", "cpu")
    invalid._model = FakeModel(128)
    with pytest.raises(ValueError, match="dimension 128"):
        invalid.get_embedding_dimension()


def test_candidate_query_skip_existing_force_source_and_keyset() -> None:
    after_id = uuid4()
    skipped = str(
        candidate_statement(source="aau-etd", force=False, after_id=after_id, limit=300).compile(
            dialect=postgresql.dialect()
        )
    )
    forced = str(
        candidate_statement(source="aau-etd", force=True).compile(dialect=postgresql.dialect())
    )
    assert "publications.embedding IS NULL" in skipped
    assert "publications.source" in skipped
    assert "publications.id >" in skipped
    assert "publications.embedding IS NULL" not in forced
    assert "ORDER BY publications.id" in skipped


def test_semantic_query_uses_pgvector_and_source_filter() -> None:
    sql = str(
        semantic_search_statement(
            [0.0] * 384,
            limit=10,
            source="aau-etd",
            min_similarity=0.4,
        ).compile(dialect=postgresql.dialect())
    )
    assert "publications.embedding <=>" in sql
    assert "publications.embedding IS NOT NULL" in sql
    assert "publications.is_deleted IS false" in sql
    assert "publications.source" in sql
    assert "ORDER BY publications.embedding <=>" in sql


def test_similarity_query_uses_pgvector_and_supported_filters() -> None:
    publication_id = uuid4()
    sql = str(
        publication_similarity_statement(
            [0.0] * 384,
            publication_id=publication_id,
            limit=6,
            minimum_score=0.35,
            university_id=uuid4(),
            year_from=2020,
            year_to=2025,
            publication_type="Thesis",
        ).compile(dialect=postgresql.dialect())
    )
    assert "publications.embedding <=>" in sql
    assert "publications.id !=" in sql
    assert "publications.embedding IS NOT NULL" in sql
    assert "publications.is_deleted IS false" in sql
    assert "repositories.university_id" in sql
    assert "publications.publication_year >=" in sql
    assert "publications.publication_year <=" in sql
    assert "publication_types" in sql
    assert "ORDER BY publications.embedding <=>" in sql


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": 51},
        {"minimum_score": -0.1},
        {"minimum_score": 1.1},
        {"year_from": 2025, "year_to": 2020},
    ],
)
def test_similarity_input_validation(kwargs: dict[str, object]) -> None:
    service = PublicationSimilarityService(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(service.similar(uuid4(), **kwargs))  # type: ignore[arg-type]


def test_processor_respects_database_batch_boundaries() -> None:
    pages = [
        [
            Publication(id=uuid4(), title=f"Title {index}", source="aau-etd", source_type="test")
            for index in range(2)
        ],
        [Publication(id=uuid4(), title="Title 3", source="aau-etd", source_type="test")],
    ]
    pages[0].sort(key=lambda item: item.id)
    session = FakeEmbeddingSession(pages)
    encoder = FakeEncoder()
    result = asyncio.run(
        PublicationEmbeddingProcessor(session, encoder).run(
            source="aau-etd", database_batch_size=2, batch_size=1
        )
    )
    assert result.processed == 3
    assert session.commit_count == 2
    assert all(item.embedding_model == "test-model" for page in pages for item in page)


def test_processor_preserves_committed_page_when_later_model_batch_fails() -> None:
    pages = [
        [Publication(id=uuid4(), title="First", source="aau-etd", source_type="test")],
        [Publication(id=uuid4(), title="Second", source="aau-etd", source_type="test")],
    ]
    session = FakeEmbeddingSession(pages)
    encoder = FakeEncoder()
    encoder.fail_on_call = 2
    with pytest.raises(RuntimeError, match="model failure"):
        asyncio.run(
            PublicationEmbeddingProcessor(session, encoder).run(
                source="aau-etd", database_batch_size=1
            )
        )
    assert session.commit_count == 1
    assert session.rollback_count == 1


@pytest.mark.parametrize(
    ("limit", "minimum"),
    [(0, None), (51, None), (10, -0.1), (10, 1.1)],
)
def test_semantic_search_input_validation(limit: int, minimum: float | None) -> None:
    service = SemanticSearchService(None, FakeEncoder())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(service.search("query", limit=limit, min_similarity=minimum))


def test_semantic_search_rejects_blank_query_before_database() -> None:
    service = SemanticSearchService(None, FakeEncoder())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="blank"):
        asyncio.run(service.search(" \n "))


def test_semantic_response_excludes_raw_vectors() -> None:
    result = SemanticSearchResult(
        id=uuid4(),
        title="Research",
        abstract_preview="Preview",
        publication_year=2024,
        source="aau-etd",
        article_url="https://example.org",
        similarity=0.83456,
    )
    response = SemanticSearchResponse(query="research", model="test", count=1, results=[result])
    payload = response.model_dump()
    assert "embedding" not in payload["results"][0]
    assert payload["results"][0]["similarity"] == 0.83456


def test_semantic_schema_rejects_invalid_result() -> None:
    with pytest.raises(ValidationError):
        SemanticSearchResult.model_validate({"title": "missing required fields"})


def test_similarity_response_excludes_raw_vectors() -> None:
    publication_id = uuid4()
    result = SimilarPublicationResult(
        id=uuid4(),
        title="Related research",
        source="aau-etd",
        similarity_score=0.81234,
        shared_keywords=["soil"],
        explanation=["Ranked by cosine similarity."],
    )
    payload = PublicationSimilarityResponse(
        publication_id=publication_id,
        model="test-model",
        count=1,
        results=[result],
    ).model_dump()
    assert "embedding" not in payload["results"][0]
    assert payload["results"][0]["similarity_score"] == 0.81234
