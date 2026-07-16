"""Generate resumable pgvector embeddings for ResearchHub publications."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from uuid import UUID

from researchhub.application.embeddings import PublicationEmbeddingProcessor
from researchhub.infrastructure.persistence.session import SessionLocal
from researchhub_ai.embeddings import DEFAULT_MODEL, get_embedding_service


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--source")
    parser.add_argument("--university-id")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--database-batch-size", type=int, default=300)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--missing-only", action="store_true")
    parser.add_argument("--failed-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict[str, object]:
    encoder = get_embedding_service(args.model, args.device)
    async with SessionLocal() as session:
        processor = PublicationEmbeddingProcessor(session, encoder, device=args.device)
        result = await processor.run(
            source=args.source,
            university_id=UUID(args.university_id) if args.university_id else None,
            batch_size=args.batch_size,
            database_batch_size=args.database_batch_size,
            limit=args.limit,
            force=args.force,
            failed_only=args.failed_only,
            dry_run=args.dry_run,
        )
    return result.asdict()


def main() -> int:
    args = parse_arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        print(json.dumps(asyncio.run(run(args)), indent=2))
        return 0
    except KeyboardInterrupt:
        print("Embedding generation interrupted; committed batches are preserved.")
        return 130
    except Exception:
        logging.getLogger(__name__).exception("Embedding generation failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
