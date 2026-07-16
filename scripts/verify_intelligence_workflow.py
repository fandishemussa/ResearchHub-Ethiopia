"""Verify one publication's document, summary, embedding, and similarity workflow."""

from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from researchhub.application.research_intelligence import ResearchIntelligenceService
from researchhub.application.services import PublicationSimilarityService
from researchhub.infrastructure.persistence.session import SessionLocal


async def run(publication_id: UUID) -> dict[str, object]:
    async with SessionLocal() as session:
        summary = await ResearchIntelligenceService(session).summarize(
            publication_id,
            "structured",
            5000,
            summary_scope="full_text",
        )
        target, similar = await PublicationSimilarityService(session).similar(
            publication_id, limit=5, minimum_score=0.0
        )
        return {
            "publication_id": str(publication_id),
            "publication_embedding": target.embedding is not None,
            "embedding_model": target.embedding_model,
            "research_document_id": str(summary.research_document_id)
            if summary.research_document_id
            else None,
            "document_status": summary.document_status,
            "summary_status": summary.status,
            "summary_source": summary.source_type,
            "summary_has_page_references": "[p. " in (summary.summary_text or ""),
            "pages_used": summary.pages_used or [],
            "chunk_count": summary.chunk_count,
            "similar_publications": len(similar),
            "current_publication_excluded": all(item["id"] != publication_id for item in similar),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publication_id", type=UUID)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.publication_id)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
