"""Unit coverage for resource-aware local Ollama context management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast

import httpx
import pytest
from pydantic import ValidationError
from researchhub.core.config import Settings
from researchhub_ai.chat import SYSTEM_PROMPT, ChatSource, GroundedLLMProvider
from researchhub_ai.context import (
    ConservativeTokenEstimator,
    ContextManager,
    ContextPolicy,
    ResourceMode,
)
from researchhub_ai.providers import (
    AIProvider,
    OllamaAIProvider,
    OllamaResourceError,
    TextGeneration,
)


@dataclass(frozen=True)
class Source:
    publication_id: str
    title: str
    text: str
    document_id: str | None = None
    chunk_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    chunk_index: int | None = None
    similarity: float | None = 0.8


SYSTEM = "Use only evidence and cite it with short labels."


def source(index: int, text: str | None = None, **changes: object) -> Source:
    values: dict[str, object] = {
        "publication_id": f"publication-{index}",
        "document_id": f"document-{index // 2}",
        "chunk_id": f"chunk-{index}",
        "chunk_index": index,
        "title": f"A long academic title for Ethiopian university research number {index}",
        "text": text
        or ("The study reports a significant finding about maternal health access. " * 12),
        "similarity": 0.9 - index / 100,
    }
    values.update(changes)
    return Source(**values)  # type: ignore[arg-type]


def manager(*, memory: int | None = 8000, **changes: object) -> ContextManager:
    policy = ContextPolicy(**changes)  # type: ignore[arg-type]
    return ContextManager(policy, memory_probe=lambda: memory)


def test_context_budget_reserves_output_and_safety_tokens() -> None:
    result = manager().prepare("What was found?", [source(1)], system_prompt=SYSTEM)
    assert result.budget.available_evidence_tokens <= 2600
    assert result.budget.response_reserve_tokens == 600
    assert result.budget.safety_margin_tokens == 300


def test_question_that_nearly_fills_context_does_not_overflow() -> None:
    result = manager().prepare("question " * 3500, [source(1)], system_prompt=SYSTEM)
    assert result.budget.available_evidence_tokens == 0
    assert not result.evidence


def test_oversized_chunk_is_extractively_compressed() -> None:
    text = (
        "Background sentence without relevance. " * 300
        + "The result was significant at 72 percent."
    )
    result = manager(max_chunk_tokens=180, target_chunk_tokens=150).prepare(
        "What significant result was reported?", [source(1, text)], system_prompt=SYSTEM
    )
    assert result.compression_count == 1
    assert result.evidence[0].token_count <= 180
    assert "72" in result.evidence[0].text


def test_no_retrieved_evidence_is_insufficient() -> None:
    assert manager().prepare("question", [], system_prompt=SYSTEM).insufficient


def test_one_relevant_chunk_is_preserved() -> None:
    result = manager().prepare("maternal health", [source(1)], system_prompt=SYSTEM)
    assert len(result.evidence) == 1


def test_more_than_twenty_candidates_still_selects_at_most_six() -> None:
    result = manager(rerank_top_k=6).prepare(
        "maternal health", [source(index) for index in range(30)], system_prompt=SYSTEM
    )
    assert result.candidate_count == 30
    assert len(result.evidence) <= 6


def test_exact_duplicate_chunks_are_removed() -> None:
    duplicate = "Identical evidence about agricultural productivity and rainfall."
    result = manager().prepare(
        "rainfall", [source(1, duplicate), source(2, duplicate)], system_prompt=SYSTEM
    )
    assert result.duplicate_count == 1
    assert len(result.evidence) == 1


def test_near_duplicate_chunks_are_removed() -> None:
    first = "The survey found improved access to primary health services in rural districts."
    second = first + " "
    result = manager().prepare(
        "health access", [source(1, first), source(2, second)], system_prompt=SYSTEM
    )
    assert result.duplicate_count == 1


def test_adjacent_overlapping_chunks_are_penalized() -> None:
    repeated = "maternal health access service quality district survey result " * 20
    result = manager(duplicate_removal=False).prepare(
        "maternal health",
        [
            source(1, repeated, document_id="same"),
            source(2, repeated + " extra", document_id="same"),
        ],
        system_prompt=SYSTEM,
    )
    assert result.overlap_count >= 1


def test_history_keeps_only_latest_two_turns() -> None:
    turns = [
        [("user", f"question {index}"), ("assistant", f"answer {index}")] for index in range(4)
    ]
    history = [item for turn in turns for item in turn]
    result = manager().prepare("follow up", [source(1)], system_prompt=SYSTEM, history=history)
    assert len(result.history) <= 4
    assert result.history[-1][1] == "answer 3"


def test_history_token_limit_drops_old_turns() -> None:
    history = [("user", "old " * 500), ("assistant", "recent concise answer")]
    result = manager(max_history_tokens=30).prepare(
        "follow up", [source(1)], system_prompt=SYSTEM, history=history
    )
    assert result.budget.history_tokens <= 30


def test_output_reservation_reduces_evidence_budget() -> None:
    low = manager(response_reserve=200, max_context_tokens=3500).prepare(
        "question", [source(1)], system_prompt=SYSTEM
    )
    high = manager(response_reserve=1000, max_context_tokens=3500).prepare(
        "question", [source(1)], system_prompt=SYSTEM
    )
    assert high.budget.available_evidence_tokens < low.budget.available_evidence_tokens


@pytest.mark.parametrize(
    "values",
    [
        {"ollama_min_num_ctx": 4096, "ollama_max_num_ctx": 2048},
        {"rag_max_context_tokens": 4096},
        {"ollama_num_predict": 600, "ollama_max_num_predict": 300},
        {"rag_target_chunk_tokens": 900, "rag_max_chunk_tokens": 800},
    ],
)
def test_configuration_validation(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Settings(**values)


def test_normal_memory_mode() -> None:
    assert manager(memory=8192).resource_profile().mode is ResourceMode.NORMAL


def test_low_memory_mode_reduces_context_and_chunks() -> None:
    profile = manager(memory=3000).resource_profile()
    assert profile.mode is ResourceMode.LOW_MEMORY
    assert (profile.num_ctx, profile.num_predict, profile.max_chunks) == (2048, 300, 3)


def test_critical_memory_mode_rejects_model_context() -> None:
    result = manager(memory=1000).prepare("question", [source(1)], system_prompt=SYSTEM)
    assert result.profile.mode is ResourceMode.CRITICAL
    assert not result.evidence


def test_citation_labels_are_renumbered_after_duplicates_removed() -> None:
    result = manager().prepare(
        "health",
        [source(1, "same"), source(2, "same"), source(3, "unique health evidence")],
        system_prompt=SYSTEM,
    )
    assert [item.label for item in result.evidence] == [
        f"S{index}" for index in range(1, len(result.evidence) + 1)
    ]
    assert {item.source.chunk_id for item in result.evidence} == {"chunk-1", "chunk-3"}


def test_unicode_and_multilingual_text_is_conservatively_counted() -> None:
    estimator = ConservativeTokenEstimator()
    text = "የኢትዮጵያ የምርምር ውጤት — naïve café 研究"
    assert estimator.count_tokens(text) >= len(text.encode("utf-8")) // 3


def test_long_metadata_is_included_in_budget_not_evidence_text() -> None:
    item = source(1, title="A" * 1000, section="Results and quantitative analysis")
    result = manager().prepare("results", [item], system_prompt=SYSTEM)
    assert result.budget.source_metadata_tokens > 100


class ExplodingClient:
    async def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    async def get(self, *_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")


def test_ollama_semaphore_is_released_after_exception() -> None:
    async def run() -> None:
        provider = OllamaAIProvider("http://ollama", "qwen2.5:7b", 1, queue_timeout=0.1)
        await provider._client.aclose()
        provider._client = ExplodingClient()  # type: ignore[assignment]
        for _ in range(2):
            with pytest.raises(httpx.ReadTimeout):
                await provider.generate_chat_response([{"role": "user", "content": "test"}])
        assert provider._semaphore._value == 1

    asyncio.run(run())


def test_ollama_options_are_clamped_to_hard_caps() -> None:
    provider = OllamaAIProvider(
        "http://ollama", "qwen2.5:7b", 1, max_num_ctx=4096, max_num_predict=600
    )
    options = provider._options({"num_ctx": 32000, "num_predict": 5000})
    asyncio.run(provider._client.aclose())
    assert options["num_ctx"] == 4096
    assert options["num_predict"] == 600


def test_oom_retry_rebuilds_a_low_memory_prompt_once() -> None:
    class OomOnceProvider:
        def __init__(self) -> None:
            self.options: list[dict[str, object]] = []

        async def generate_chat_response(
            self,
            messages: list[dict[str, str]],
            *,
            model: str | None = None,
            options: dict[str, object] | None = None,
        ) -> TextGeneration:
            del messages
            self.options.append(options or {})
            if len(self.options) == 1:
                raise OllamaResourceError("out of memory")
            return TextGeneration("Answer [S1]", model or "qwen2.5:7b", "ollama")

    raw = [source(index) for index in range(8)]
    prepared = manager().prepare("maternal health", raw, system_prompt=SYSTEM_PROMPT)
    chat_sources = [
        ChatSource(item.publication_id, item.title, evidence.text)
        for item, evidence in zip(raw, prepared.evidence, strict=False)
    ]
    provider = OomOnceProvider()
    result = asyncio.run(
        GroundedLLMProvider(cast(AIProvider, provider), model="qwen2.5:7b").complete(
            "maternal health", chat_sources, prepared=prepared
        )
    )
    assert len(provider.options) == 2
    assert provider.options[1]["num_ctx"] == 2048
    assert provider.options[1]["num_predict"] == 300
    assert result.answer == "Answer [1]"
    assert result.diagnostics and result.diagnostics["resource_mode"] == "LOW_MEMORY"


def test_only_one_ollama_generation_is_active_concurrently() -> None:
    class TrackingClient:
        def __init__(self) -> None:
            self.active = 0
            self.peak = 0

        async def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
            self.active += 1
            self.peak = max(self.peak, self.active)
            await asyncio.sleep(0.02)
            self.active -= 1
            return httpx.Response(
                200,
                json={"model": "qwen2.5:7b", "message": {"content": "ok"}},
                request=httpx.Request("POST", "http://ollama/api/chat"),
            )

    async def run() -> None:
        provider = OllamaAIProvider("http://ollama", "qwen2.5:7b", 1, max_concurrent=1)
        await provider._client.aclose()
        client = TrackingClient()
        provider._client = client  # type: ignore[assignment]
        await asyncio.gather(
            provider.generate_chat_response([{"role": "user", "content": "one"}]),
            provider.generate_chat_response([{"role": "user", "content": "two"}]),
        )
        assert client.peak == 1

    asyncio.run(run())
