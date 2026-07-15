"""Tests for shared AI provider and publication text foundations."""

from __future__ import annotations

from uuid import uuid4

import pytest
from researchhub.infrastructure.persistence.models import (
    Author,
    Journal,
    Keyword,
    Publication,
    PublicationAuthor,
    PublicationKeyword,
)
from researchhub_ai.providers import LocalAIProvider, create_ai_provider
from researchhub_ai.text_builder import PublicationTextBuilder, clean_ai_text


def test_text_builder_normalizes_all_supported_metadata_and_hashes_deterministically() -> None:
    publication = Publication(
        id=uuid4(),
        title="  Soil <b>health</b>  ",
        abstract="Water &amp; soil\r\nquality.",
        subjects=["Agriculture", "Agriculture"],
        publication_year=2024,
        source="test",
        source_type="test",
        is_deleted=False,
    )
    publication.journal = Journal(id=uuid4(), name="Ethiopian Journal", university_id=None)
    author = Author(id=uuid4(), full_name="Aster Bekele")
    keyword = Keyword(id=uuid4(), term="soil health", normalized_term="soil health")
    publication.authors = [PublicationAuthor(id=uuid4(), author=author)]
    publication.keywords = [PublicationKeyword(id=uuid4(), keyword=keyword)]
    builder = PublicationTextBuilder()

    first = builder.build_embedding_text(publication)
    second = builder.build_embedding_text(publication)

    assert "Title:\nSoil health" in first.text
    assert "Water & soil" in first.text
    assert "Authors:\nAster Bekele" in first.text
    assert first.content_hash == second.content_hash
    assert len(first.content_hash) == 64


def test_text_builder_excludes_deleted_publications() -> None:
    publication = Publication(title="Deleted", source="test", source_type="test", is_deleted=True)
    with pytest.raises(ValueError, match="Deleted"):
        PublicationTextBuilder().build_chatbot_document(publication)


def test_clean_ai_text_decodes_entities_and_removes_markup() -> None:
    assert clean_ai_text("<p>Health &amp; water</p>") == "Health & water"


def test_provider_factory_rejects_incomplete_remote_configuration() -> None:
    with pytest.raises(ValueError, match="AI_CHAT_MODEL"):
        create_ai_provider("ollama", embedding_model="model")
    with pytest.raises(ValueError, match="base URL"):
        create_ai_provider("openai", embedding_model="model", chat_model="chat")


def test_provider_factory_creates_local_provider_without_remote_secrets() -> None:
    provider = create_ai_provider("local", embedding_model="test-model")
    assert isinstance(provider, LocalAIProvider)
