"""Resource-aware, deterministic context selection for grounded chat."""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Protocol


class ResourceMode(StrEnum):
    NORMAL = "NORMAL"
    LOW_MEMORY = "LOW_MEMORY"
    CRITICAL = "CRITICAL"


class ContextSource(Protocol):
    publication_id: str
    title: str
    text: str
    document_id: str | None
    chunk_id: str | None
    page_start: int | None
    page_end: int | None
    section: str | None
    chunk_index: int | None
    similarity: float | None


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    num_ctx: int = 4096
    min_num_ctx: int = 2048
    max_num_ctx: int = 4096
    num_predict: int = 500
    max_num_predict: int = 600
    rerank_top_k: int = 5
    max_chunks: int = 6
    max_chunk_tokens: int = 800
    target_chunk_tokens: int = 600
    response_reserve: int = 600
    safety_margin: int = 300
    min_evidence_tokens: int = 500
    max_context_tokens: int = 2600
    deduplication_threshold: float = 0.88
    adjacent_overlap_threshold: float = 0.65
    dynamic_context: bool = True
    compression: bool = True
    duplicate_removal: bool = True
    max_history_turns: int = 2
    max_history_tokens: int = 500
    min_free_memory_mb: int = 4096
    critical_free_memory_mb: int = 2048
    memory_guard: bool = True


@dataclass(frozen=True, slots=True)
class ResourceProfile:
    mode: ResourceMode
    num_ctx: int
    num_predict: int
    max_chunks: int
    max_evidence_tokens: int


@dataclass(frozen=True, slots=True)
class ContextBudget:
    model_context_limit: int
    system_prompt_tokens: int
    question_tokens: int
    history_tokens: int
    source_metadata_tokens: int
    response_reserve_tokens: int
    safety_margin_tokens: int
    available_evidence_tokens: int
    selected_evidence_tokens: int = 0
    remaining_tokens: int = 0
    truncated: bool = False
    dropped_chunk_count: int = 0


@dataclass(frozen=True, slots=True)
class SelectedEvidence:
    label: str
    source: ContextSource
    text: str
    token_count: int
    compressed: bool


@dataclass(frozen=True, slots=True)
class PreparedContext:
    profile: ResourceProfile
    budget: ContextBudget
    evidence: tuple[SelectedEvidence, ...]
    history: tuple[tuple[str, str], ...] = ()
    candidate_count: int = 0
    duplicate_count: int = 0
    overlap_count: int = 0
    compression_count: int = 0

    @property
    def insufficient(self) -> bool:
        return not self.evidence


class ConservativeTokenEstimator:
    """Portable fallback estimator that intentionally avoids under-counting.

    Qwen's tokenizer is not loaded because doing so adds a large dependency and
    memory cost. UTF-8 bytes/3 plus lexical boundaries is conservative for
    English and multilingual research text; the separate safety margin absorbs
    message-template/tokenizer differences.
    """

    _pieces = re.compile(r"\w+|[^\w\s]", re.UNICODE)

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        lexical = len(self._pieces.findall(text))
        byte_estimate = math.ceil(len(text.encode("utf-8")) / 3)
        return max(1, lexical, byte_estimate)

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0 or not text:
            return ""
        if self.count_tokens(text) <= max_tokens:
            return text.strip()
        selected: list[str] = []
        for sentence in _sentences(text):
            candidate = " ".join((*selected, sentence))
            if self.count_tokens(candidate) > max_tokens:
                break
            selected.append(sentence)
        if selected:
            return " ".join(selected).strip()
        words: list[str] = []
        for word in text.split():
            candidate = " ".join((*words, word))
            if self.count_tokens(candidate) > max_tokens:
                break
            words.append(word)
        return " ".join(words).strip()


class ContextManager:
    def __init__(
        self,
        policy: ContextPolicy,
        *,
        estimator: ConservativeTokenEstimator | None = None,
        memory_probe: Callable[[], int | None] | None = None,
    ) -> None:
        self.policy = policy
        self.estimator = estimator or ConservativeTokenEstimator()
        self.memory_probe = memory_probe or available_memory_mb

    def resource_profile(self) -> ResourceProfile:
        available = self.memory_probe() if self.policy.memory_guard else None
        if available is not None and available < self.policy.critical_free_memory_mb:
            return ResourceProfile(ResourceMode.CRITICAL, self.policy.min_num_ctx, 0, 0, 0)
        if available is not None and available < self.policy.min_free_memory_mb:
            return ResourceProfile(
                ResourceMode.LOW_MEMORY,
                self.policy.min_num_ctx,
                min(300, self.policy.max_num_predict),
                min(3, self.policy.max_chunks),
                max(self.policy.min_evidence_tokens, self.policy.min_num_ctx // 2),
            )
        return ResourceProfile(
            ResourceMode.NORMAL,
            min(max(self.policy.num_ctx, self.policy.min_num_ctx), self.policy.max_num_ctx),
            min(self.policy.num_predict, self.policy.max_num_predict),
            min(self.policy.rerank_top_k, self.policy.max_chunks),
            self.policy.max_context_tokens,
        )

    def prepare(
        self,
        question: str,
        sources: Iterable[ContextSource],
        *,
        system_prompt: str,
        history: Iterable[tuple[str, str]] = (),
    ) -> PreparedContext:
        candidates = list(sources)
        profile = self.resource_profile()
        if profile.mode is ResourceMode.CRITICAL:
            return PreparedContext(
                profile,
                self._empty_budget(profile, question, system_prompt),
                (),
                candidate_count=len(candidates),
            )

        limited_history = self._limit_history(history)
        fixed_history = "\n".join(f"{role}: {content}" for role, content in limited_history)
        system_tokens = self.estimator.count_tokens(system_prompt)
        question_tokens = self.estimator.count_tokens(question)
        history_tokens = self.estimator.count_tokens(fixed_history)

        ranked, duplicates, overlaps = self._filter_and_rank(question, candidates)
        metadata_tokens = sum(
            self.estimator.count_tokens(_metadata(source))
            for source in ranked[: profile.max_chunks]
        )
        available = max(
            0,
            min(
                profile.max_evidence_tokens,
                profile.num_ctx
                - system_tokens
                - question_tokens
                - history_tokens
                - metadata_tokens
                - self.policy.response_reserve
                - self.policy.safety_margin,
            ),
        )
        selected: list[SelectedEvidence] = []
        used = 0
        compression_count = 0
        for source in ranked:
            if len(selected) >= profile.max_chunks:
                break
            remaining = available - used
            if remaining <= 0:
                break
            maximum = min(self.policy.max_chunk_tokens, remaining)
            text = _strip_boilerplate(source.text)
            compressed = False
            if self.estimator.count_tokens(text) > maximum and self.policy.compression:
                text = _compress(question, text, maximum, self.estimator)
                compressed = True
            else:
                text = self.estimator.truncate_to_tokens(text, maximum)
            tokens = self.estimator.count_tokens(text)
            if not text or tokens > remaining:
                continue
            selected.append(
                SelectedEvidence(f"S{len(selected) + 1}", source, text, tokens, compressed)
            )
            used += tokens
            compression_count += int(compressed)

        dropped = max(0, len(candidates) - len(selected))
        budget = ContextBudget(
            model_context_limit=profile.num_ctx,
            system_prompt_tokens=system_tokens,
            question_tokens=question_tokens,
            history_tokens=history_tokens,
            source_metadata_tokens=metadata_tokens,
            response_reserve_tokens=self.policy.response_reserve,
            safety_margin_tokens=self.policy.safety_margin,
            available_evidence_tokens=available,
            selected_evidence_tokens=used,
            remaining_tokens=max(0, available - used),
            truncated=dropped > 0 or compression_count > 0,
            dropped_chunk_count=dropped,
        )
        return PreparedContext(
            profile,
            budget,
            tuple(selected),
            tuple(limited_history),
            len(candidates),
            duplicates,
            overlaps,
            compression_count,
        )

    def _filter_and_rank(
        self, question: str, sources: list[ContextSource]
    ) -> tuple[list[ContextSource], int, int]:
        query = set(_terms(question))
        scored: list[tuple[float, int, ContextSource]] = []
        seen: list[tuple[str, ContextSource]] = []
        duplicates = 0
        overlaps = 0
        for position, source in enumerate(sources):
            normalized = _normalize(source.text)
            duplicate = any(
                normalized == prior
                or SequenceMatcher(None, normalized[:5000], prior[:5000]).ratio()
                >= self.policy.deduplication_threshold
                for prior, _ in seen
            )
            if duplicate and self.policy.duplicate_removal:
                duplicates += 1
                continue
            overlap_penalty = 0.0
            for prior_text, prior_source in seen:
                adjacent = (
                    source.document_id
                    and source.document_id == prior_source.document_id
                    and source.chunk_index is not None
                    and prior_source.chunk_index is not None
                    and abs(source.chunk_index - prior_source.chunk_index) == 1
                )
                ratio = _jaccard(set(_terms(normalized)), set(_terms(prior_text)))
                if adjacent and ratio >= self.policy.adjacent_overlap_threshold:
                    overlap_penalty = max(overlap_penalty, 0.2)
                    overlaps += 1
            seen.append((normalized, source))
            lexical = _jaccard(query, set(_terms(source.title + " " + source.text[:4000])))
            semantic = source.similarity if source.similarity is not None else 0.0
            score = semantic * 0.65 + lexical * 0.35 - overlap_penalty - position * 0.0001
            scored.append((score, -position, source))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored], duplicates, overlaps

    def _limit_history(self, history: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
        items = list(history)[-(self.policy.max_history_turns * 2) :]
        selected: list[tuple[str, str]] = []
        used = 0
        for role, content in reversed(items):
            tokens = self.estimator.count_tokens(content)
            if used + tokens > self.policy.max_history_tokens:
                continue
            selected.append((role, content))
            used += tokens
        return list(reversed(selected))

    def _empty_budget(
        self, profile: ResourceProfile, question: str, system_prompt: str
    ) -> ContextBudget:
        return ContextBudget(
            profile.num_ctx,
            self.estimator.count_tokens(system_prompt),
            self.estimator.count_tokens(question),
            0,
            0,
            self.policy.response_reserve,
            self.policy.safety_margin,
            0,
        )


def _compress(question: str, text: str, limit: int, estimator: ConservativeTokenEstimator) -> str:
    query_terms = set(_terms(question))
    ranked: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(_sentences(text)):
        terms = set(_terms(sentence))
        score = len(query_terms & terms) * 3.0
        lowered = sentence.casefold()
        score += (
            sum(
                marker in lowered
                for marker in (
                    "result",
                    "finding",
                    "conclusion",
                    "significant",
                    "recommend",
                    "method",
                )
            )
            * 2
        )
        score += 2 if re.search(r"\b\d+(?:\.\d+)?%?\b", sentence) else 0
        ranked.append((score, -index, sentence))
    ranked.sort(reverse=True)
    chosen: list[tuple[int, str]] = []
    used = 0
    for _, negative_index, sentence in ranked:
        tokens = estimator.count_tokens(sentence)
        if used + tokens > limit:
            continue
        chosen.append((-negative_index, sentence))
        used += tokens
        if used >= min(limit, 400):
            break
    chosen.sort()
    return " ".join(sentence for _, sentence in chosen)


def _metadata(source: ContextSource) -> str:
    values = [source.title, source.document_id or "", source.section or ""]
    if source.page_start is not None:
        values.append(f"pages {source.page_start}-{source.page_end or source.page_start}")
    return " ".join(value for value in values if value)


def _strip_boilerplate(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    kept = [
        line
        for line in lines
        if line
        and not line.casefold().startswith(
            ("repository source:", "copyright ©", "all rights reserved", "navigation:")
        )
    ]
    return " ".join(kept)


def _normalize(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


def _terms(text: str) -> list[str]:
    return [term for term in re.findall(r"\w+", text.casefold(), re.UNICODE) if len(term) > 2]


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def available_memory_mb() -> int | None:
    """Return portable available-memory estimate without a mandatory dependency."""

    try:
        import psutil  # type: ignore[import-untyped]

        return int(psutil.virtual_memory().available / (1024 * 1024))
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong),
                    ("avail_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.avail_phys / (1024 * 1024))
        except (AttributeError, OSError):
            return None
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            match = re.search(r"^MemAvailable:\s+(\d+)\s+kB", handle.read(), re.MULTILINE)
            return int(match.group(1)) // 1024 if match else None
    except OSError:
        return None
