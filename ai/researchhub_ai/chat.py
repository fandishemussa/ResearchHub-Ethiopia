"""Provider-neutral grounded chat completion contracts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Any, Protocol

import httpx

from researchhub_ai.context import ConservativeTokenEstimator, PreparedContext, ResourceMode
from researchhub_ai.providers import AIProvider, OllamaQueueTimeout, OllamaResourceError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are ResearchHub Ethiopia's grounded academic assistant. "
    "Use only the supplied evidence. Cite claims with [S1], [S2], etc. "
    "Do not invent facts, quotations, statistics, authors, dates, pages, or citations. "
    "When evidence is insufficient, state exactly what is missing."
)


class ChatResourceUnavailable(RuntimeError):
    """Raised when local resources are too constrained for safe generation."""


@dataclass(frozen=True, slots=True)
class ChatSource:
    publication_id: str
    title: str
    text: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    chunk_index: int | None = None
    similarity: float | None = None


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    answer: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    diagnostics: dict[str, Any] | None = None


class ChatProvider(Protocol):
    async def complete(
        self, question: str, sources: list[ChatSource], *, prepared: PreparedContext | None = None
    ) -> ChatCompletion: ...


class FallbackChatProvider:
    """Use an offline grounded provider when an optional remote provider fails."""

    def __init__(self, primary: ChatProvider, fallback: ChatProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    async def complete(
        self, question: str, sources: list[ChatSource], *, prepared: PreparedContext | None = None
    ) -> ChatCompletion:
        try:
            if prepared is None:
                return await self.primary.complete(question, sources)
            return await self.primary.complete(question, sources, prepared=prepared)
        except (ChatResourceUnavailable, OllamaQueueTimeout, OllamaResourceError):
            raise
        except (httpx.HTTPError, OSError, TimeoutError, RuntimeError) as exc:
            logger.warning(
                "Primary chat provider unavailable; using grounded local fallback: %s",
                type(exc).__name__,
            )
            if prepared is None:
                return await self.fallback.complete(question, sources)
            return await self.fallback.complete(question, sources, prepared=prepared)


class GroundedLLMProvider:
    """Grounded adapter for Ollama/OpenAI-compatible providers."""

    def __init__(self, provider: AIProvider, *, model: str, max_context_chars: int = 28000) -> None:
        self.provider = provider
        self.model = model
        self.max_context_chars = max_context_chars

    async def complete(
        self, question: str, sources: list[ChatSource], *, prepared: PreparedContext | None = None
    ) -> ChatCompletion:
        if prepared and prepared.profile.mode is ResourceMode.CRITICAL:
            raise ChatResourceUnavailable(
                "Local AI resources are temporarily insufficient. Close memory-intensive applications and retry."
            )
        if not sources:
            return ChatCompletion(
                answer="I could not find enough indexed research evidence to answer that question.",
                model=self.model,
            )

        context_parts: list[str] = []
        for index, source in enumerate(sources, start=1):
            label = (
                prepared.evidence[index - 1].label
                if prepared and index <= len(prepared.evidence)
                else f"S{index}"
            )
            lines = [f"[{label}]", f"title: {source.title}"]
            if source.document_id:
                lines.append(f"document_id: {source.document_id}")
            if source.page_start is not None:
                pages = (
                    str(source.page_start)
                    if source.page_end in (None, source.page_start)
                    else f"{source.page_start}-{source.page_end}"
                )
                lines.append(f"pages: {pages}")
            if source.section:
                lines.append(f"section: {source.section}")
            lines.append(f"text: {source.text.strip()}")
            context_parts.append("\n".join(lines))

        context = "\n\n".join(context_parts)
        prompt = f"""USER QUESTION:
{question}

EVIDENCE:
{context}

ANSWER REQUIREMENTS:
- Answer the question directly.
- Cite factual claims.
- Distinguish evidence from interpretation.
- Do not include generic limitations when the evidence is sufficient.
"""
        options = None
        if prepared:
            options = {
                "num_ctx": prepared.profile.num_ctx,
                "num_predict": prepared.profile.num_predict,
            }
        try:
            result = await self.provider.generate_chat_response(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
                options=options,
            )
        except OllamaResourceError:
            if not prepared or prepared.profile.mode is not ResourceMode.NORMAL:
                raise
            estimator = ConservativeTokenEstimator()
            degraded_evidence = tuple(
                replace(
                    evidence,
                    text=estimator.truncate_to_tokens(evidence.text, 250),
                    token_count=min(evidence.token_count, 250),
                    compressed=True,
                )
                for evidence in prepared.evidence[:3]
            )
            degraded = replace(
                prepared,
                profile=replace(
                    prepared.profile,
                    mode=ResourceMode.LOW_MEMORY,
                    num_ctx=2048,
                    num_predict=300,
                    max_chunks=3,
                    max_evidence_tokens=750,
                ),
                budget=replace(
                    prepared.budget,
                    model_context_limit=2048,
                    available_evidence_tokens=750,
                    selected_evidence_tokens=sum(item.token_count for item in degraded_evidence),
                    truncated=True,
                    dropped_chunk_count=max(
                        prepared.budget.dropped_chunk_count,
                        prepared.candidate_count - len(degraded_evidence),
                    ),
                ),
                evidence=degraded_evidence,
                compression_count=prepared.compression_count + len(degraded_evidence),
            )
            degraded_sources = [
                replace(source, text=evidence.text)
                for source, evidence in zip(sources[:3], degraded_evidence, strict=True)
            ]
            logger.warning("ollama_oom_degraded_retry selected_chunks=%d", len(degraded_sources))
            return await self.complete(question, degraded_sources, prepared=degraded)
        answer = re.sub(r"\[S(\d+)\]", r"[\1]", result.text.strip())
        return ChatCompletion(
            answer=answer,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            diagnostics=_diagnostics(prepared, result.prompt_tokens),
        )


class GroundedLocalProvider:
    """Offline extractive fallback for environments without a local LLM."""

    model_name = "grounded-local-v2"

    async def complete(
        self, question: str, sources: list[ChatSource], *, prepared: PreparedContext | None = None
    ) -> ChatCompletion:
        if prepared and prepared.profile.mode is ResourceMode.CRITICAL:
            raise ChatResourceUnavailable(
                "Local AI resources are temporarily insufficient. Please retry shortly."
            )
        usable = [source for source in sources if _clean(source.text)]
        if not usable:
            answer = "I could not find enough indexed research evidence to answer that question."
            return ChatCompletion(
                answer=answer, model=self.model_name, completion_tokens=_estimate_tokens(answer)
            )

        primary_title = usable[0].title
        same_document = [
            source
            for source in usable
            if _normalize_title(source.title) == _normalize_title(primary_title)
        ]
        evidence = " ".join(_remove_metadata(source.text) for source in same_document)
        sentences = _rank_sentences(question, evidence, limit=8)

        if not sentences:
            answer = (
                f"The most relevant retrieved study was “{primary_title}”, but the indexed excerpts did not contain "
                "enough readable detail for a reliable explanation."
            )
        else:
            answer = "\n\n".join(
                [
                    f"## Direct answer\n\nThe most relevant study is **{primary_title}**. [1]",
                    "## Evidence from the study\n\n" + " ".join(sentences[:3]) + " [1]",
                    "## Main findings\n\n"
                    + "\n".join(f"- {sentence} [1]" for sentence in sentences[3:7]),
                    "## Interpretation\n\nThese findings should be interpreted within the study's own sample, branches, methods, and time period.",
                ]
            )

        prompt_text = question + " " + " ".join(source.text for source in usable)
        return ChatCompletion(
            answer=answer,
            model=self.model_name,
            prompt_tokens=_estimate_tokens(prompt_text),
            completion_tokens=_estimate_tokens(answer),
            diagnostics=_diagnostics(prepared, _estimate_tokens(prompt_text)),
        )


def _diagnostics(prepared: PreparedContext | None, prompt_tokens: int) -> dict[str, Any] | None:
    if prepared is None:
        return None
    return {
        "resource_mode": prepared.profile.mode.value,
        "configured_num_ctx": prepared.profile.num_ctx,
        "estimated_prompt_tokens": prompt_tokens
        or (
            prepared.budget.system_prompt_tokens
            + prepared.budget.question_tokens
            + prepared.budget.history_tokens
            + prepared.budget.source_metadata_tokens
            + prepared.budget.selected_evidence_tokens
        ),
        "reserved_output_tokens": prepared.profile.num_predict,
        "selected_chunks": len(prepared.evidence),
        "dropped_chunks": prepared.budget.dropped_chunk_count,
        "context_truncated": prepared.budget.truncated,
        "compressed_chunks": prepared.compression_count,
    }


def _rank_sentences(question: str, text: str, *, limit: int) -> list[str]:
    query_terms = set(_tokens(question))
    candidates = []
    for position, sentence in enumerate(re.split(r"(?<=[.!?])\s+|\n+", _clean(text))):
        sentence = sentence.strip()
        if len(sentence) < 40:
            continue
        terms = set(_tokens(sentence))
        score = len(query_terms & terms) * 4
        lowered = sentence.casefold()
        score += sum(
            2
            for marker in (
                "finding",
                "result",
                "conclusion",
                "gap",
                "servqual",
                "expectation",
                "perception",
                "recommend",
            )
            if marker in lowered
        )
        candidates.append((score, -position, sentence))
    candidates.sort(reverse=True)
    selected: list[str] = []
    for _, _, sentence in candidates:
        if len(selected) >= limit:
            break
        if sentence.casefold() not in {item.casefold() for item in selected}:
            selected.append(_punctuate(sentence))
    return selected


def _remove_metadata(text: str) -> str:
    lines = str(text).splitlines()
    if lines and lines[0].casefold().startswith("repository source:"):
        return "\n".join(lines[1:]).strip()
    return re.sub(
        r"^Repository source:\s*[^|]+(?:\s*\|\s*Pages?\s+\d+(?:-\d+)?)?(?:\s*\|\s*Similarity:\s*\d+(?:\.\d+)?)?\s*",
        "",
        str(text),
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


def _tokens(text: str) -> list[str]:
    stop = {
        "what",
        "which",
        "the",
        "and",
        "for",
        "from",
        "with",
        "were",
        "was",
        "study",
        "research",
        "paper",
    }
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) >= 3 and token not in stop
    ]


def _clean(text: str) -> str:
    return " ".join(str(text).split()).strip()


def _punctuate(text: str) -> str:
    cleaned = _clean(text)
    return cleaned if cleaned.endswith((".", "!", "?", "…")) else cleaned + "."


def _estimate_tokens(text: str) -> int:
    cleaned = _clean(text)
    return max(1, round(len(cleaned) / 4)) if cleaned else 0
