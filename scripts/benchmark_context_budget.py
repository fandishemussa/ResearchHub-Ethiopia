"""Synthetic, read-only benchmark for local RAG context budgeting."""

from __future__ import annotations

import argparse
import asyncio
import json
import tracemalloc
from dataclasses import dataclass
from time import perf_counter
from typing import cast

from researchhub_ai.chat import SYSTEM_PROMPT
from researchhub_ai.context import (
    ContextManager,
    ContextPolicy,
    ContextSource,
    available_memory_mb,
)
from researchhub_ai.providers import OllamaAIProvider


@dataclass(frozen=True)
class Candidate:
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


def candidates(count: int, *, duplicates: bool = False) -> list[Candidate]:
    result = []
    for index in range(count):
        common = (
            "The study used a cross-sectional design. The findings report a 24 percent "
            "improvement in access to university research services. "
        )
        if duplicates:
            text = common * 8
        else:
            topic = (
                "maternal health",
                "agricultural markets",
                "water governance",
                "digital libraries",
                "renewable energy",
                "public education",
            )[index % 6]
            text = common * 2 + (
                f"Evidence item {index} analyzes {topic} in region {index} using distinct variables. "
                * 8
            )
        result.append(
            Candidate(
                f"publication-{index}",
                f"Ethiopian university research evidence {index}",
                text,
                f"document-{index // 2}",
                f"chunk-{index}",
                index + 1,
                index + 1,
                "Results",
                index,
                0.95 - index / 100,
            )
        )
    return result


async def main() -> None:
    tracemalloc.start()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--call-ollama", action="store_true", help="Also make real local generation calls"
    )
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    args = parser.parse_args()
    cases = [
        ("short", "What did the study find?", candidates(3)),
        (
            "medium",
            "Compare methods and findings in maternal health access research.",
            candidates(10),
        ),
        (
            "long",
            "Explain the methods, variables, numerical findings, limitations, and recommendations. "
            * 20,
            candidates(15),
        ),
        ("many_candidates", "Synthesize evidence about research access.", candidates(30)),
        ("duplicate_evidence", "What evidence is repeated?", candidates(20, duplicates=True)),
    ]
    manager = ContextManager(ContextPolicy())
    provider = OllamaAIProvider(args.ollama_url, "qwen2.5:7b", 240) if args.call_ollama else None
    for name, question, evidence in cases:
        started = perf_counter()
        prepared = manager.prepare(
            question,
            cast(list[ContextSource], evidence),
            system_prompt=SYSTEM_PROMPT,
        )
        inference_ms: int | None = None
        generated_tokens: int | None = None
        fallback = prepared.profile.mode.value != "NORMAL"
        if provider and prepared.evidence:
            inference_started = perf_counter()
            completion = await provider.generate_chat_response(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                options={
                    "num_ctx": prepared.profile.num_ctx,
                    "num_predict": prepared.profile.num_predict,
                },
            )
            inference_ms = round((perf_counter() - inference_started) * 1000)
            generated_tokens = completion.completion_tokens
        print(
            json.dumps(
                {
                    "case": name,
                    "resource_mode": prepared.profile.mode.value,
                    "retrieved_candidates": prepared.candidate_count,
                    "selected_chunks": len(prepared.evidence),
                    "estimated_prompt_tokens": (
                        prepared.budget.system_prompt_tokens
                        + prepared.budget.question_tokens
                        + prepared.budget.history_tokens
                        + prepared.budget.source_metadata_tokens
                        + prepared.budget.selected_evidence_tokens
                    ),
                    "output_reserve": prepared.profile.num_predict,
                    "total_latency_ms": round((perf_counter() - started) * 1000),
                    "ollama_inference_ms": inference_ms,
                    "generated_tokens": generated_tokens,
                    "compression_occurred": prepared.compression_count > 0,
                    "fallback_mode": fallback,
                    "available_memory_mb": available_memory_mb(),
                    "peak_python_memory_mb": round(
                        tracemalloc.get_traced_memory()[1] / (1024 * 1024), 2
                    ),
                }
            )
        )
    if provider:
        await provider._client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
