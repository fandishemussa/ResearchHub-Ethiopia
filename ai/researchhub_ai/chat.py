"""Provider-neutral grounded chat completion contracts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from researchhub_ai.providers import AIProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChatSource:
    publication_id: str
    title: str
    text: str
    authors: tuple[str, ...] = ()
    year: int | None = None


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    answer: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatProvider(Protocol):
    async def complete(self, question: str, sources: list[ChatSource]) -> ChatCompletion: ...


class FallbackChatProvider:
    """Use an offline grounded provider when an optional remote provider fails."""

    def __init__(self, primary: ChatProvider, fallback: ChatProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    async def complete(self, question: str, sources: list[ChatSource]) -> ChatCompletion:
        try:
            return await self.primary.complete(question, sources)
        except (httpx.HTTPError, OSError, TimeoutError, RuntimeError) as exc:
            logger.warning(
                "Primary chat provider unavailable; using grounded local fallback: %s",
                type(exc).__name__,
            )
            return await self.fallback.complete(question, sources)


class GroundedLLMProvider:
    """Grounded adapter for Ollama/OpenAI-compatible providers."""

    def __init__(self, provider: AIProvider, *, model: str, max_context_chars: int = 28000) -> None:
        self.provider = provider
        self.model = model
        self.max_context_chars = max_context_chars

    async def complete(self, question: str, sources: list[ChatSource]) -> ChatCompletion:
        if not sources:
            return ChatCompletion(
                answer="I could not find enough indexed research evidence to answer that question.",
                model=self.model,
            )

        context_parts: list[str] = []
        used = 0
        for index, source in enumerate(sources, start=1):
            metadata = []
            if source.authors:
                metadata.append(", ".join(source.authors[:3]))
            if source.year:
                metadata.append(str(source.year))
            header = f"SOURCE [{index}]\nTitle: {source.title}"
            if metadata:
                header += "\nMetadata: " + " | ".join(metadata)
            block = f"{header}\nText:\n{source.text.strip()}\n"
            if used + len(block) > self.max_context_chars:
                break
            context_parts.append(block)
            used += len(block)

        context = "\n\n".join(context_parts)
        system = (
            "You are ResearchHub Ethiopia's grounded research assistant. "
            "Answer only from the supplied sources. Never invent facts, numbers, authors, methods, or conclusions. "
            "Cite claims using [1], [2], etc. Prefer the most relevant study and explain it in detail instead of listing every source. "
            "When evidence is incomplete, state exactly what is missing."
        )
        prompt = f"""Question:
{question}

Retrieved research evidence:
{context}

Write a detailed but focused answer with these sections when supported:
- Direct answer
- Study objective
- Methodology
- Main findings
- Interpretation
- Practical implications or recommendations
- Limitations stated in the study

Use inline citations such as [1]. Do not add a generic disclaimer. Do not discuss unrelated sources.
"""
        result = await self.provider.generate_chat_response(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            model=self.model,
        )
        return ChatCompletion(
            answer=result.text.strip(),
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        )


class GroundedLocalProvider:
    """Offline extractive fallback for environments without a local LLM."""

    model_name = "grounded-local-v2"

    async def complete(self, question: str, sources: list[ChatSource]) -> ChatCompletion:
        usable = [source for source in sources if _clean(source.text)]
        if not usable:
            answer = "I could not find enough indexed research evidence to answer that question."
            return ChatCompletion(answer=answer, model=self.model_name, completion_tokens=_estimate_tokens(answer))

        primary_title = usable[0].title
        same_document = [source for source in usable if _normalize_title(source.title) == _normalize_title(primary_title)]
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
                    "## Main findings\n\n" + "\n".join(f"- {sentence} [1]" for sentence in sentences[3:7]),
                    "## Interpretation\n\nThese findings should be interpreted within the study's own sample, branches, methods, and time period.",
                ]
            )

        prompt_text = question + " " + " ".join(source.text for source in usable)
        return ChatCompletion(
            answer=answer,
            model=self.model_name,
            prompt_tokens=_estimate_tokens(prompt_text),
            completion_tokens=_estimate_tokens(answer),
        )


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
        score += sum(2 for marker in ("finding", "result", "conclusion", "gap", "servqual", "expectation", "perception", "recommend") if marker in lowered)
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
    stop = {"what", "which", "the", "and", "for", "from", "with", "were", "was", "study", "research", "paper"}
    return [token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) >= 3 and token not in stop]


def _clean(text: str) -> str:
    return " ".join(str(text).split()).strip()


def _punctuate(text: str) -> str:
    cleaned = _clean(text)
    return cleaned if cleaned.endswith((".", "!", "?", "…")) else cleaned + "."


def _estimate_tokens(text: str) -> int:
    cleaned = _clean(text)
    return max(1, round(len(cleaned) / 4)) if cleaned else 0
