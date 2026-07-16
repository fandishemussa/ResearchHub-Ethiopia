"""Repair confident research-document links from downloader UUID filenames."""

from __future__ import annotations

import argparse
import asyncio
import re

from researchhub.infrastructure.persistence.models import Publication, ResearchDocument
from researchhub.infrastructure.persistence.session import SessionLocal
from sqlalchemy import func, or_, select

UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


async def run(*, apply: bool, limit: int | None) -> dict[str, int]:
    scanned = linked = ambiguous = unmatched = 0
    async with SessionLocal() as session:
        statement = (
            select(ResearchDocument)
            .where(ResearchDocument.publication_id.is_(None))
            .order_by(ResearchDocument.created_at)
        )
        if limit:
            statement = statement.limit(limit)
        documents = list((await session.scalars(statement)).all())
        for document in documents:
            scanned += 1
            searchable = " ".join(
                value
                for value in (document.external_id, document.filename, document.local_path)
                if value
            )
            match = UUID_PATTERN.search(searchable)
            candidates: list[Publication] = []
            if match:
                identifier = match.group(0)
                candidates = list(
                    (
                        await session.scalars(
                            select(Publication).where(
                                or_(
                                    func.lower(Publication.external_id).contains(
                                        identifier.casefold()
                                    ),
                                    func.lower(Publication.repository_identifier).contains(
                                        identifier.casefold()
                                    ),
                                )
                            )
                        )
                    ).all()
                )
            if not candidates and document.title:
                candidates = list(
                    (
                        await session.scalars(
                            select(Publication).where(
                                func.lower(func.trim(Publication.title))
                                == document.title.casefold().strip()
                            )
                        )
                    ).all()
                )
            if len(candidates) == 1:
                linked += 1
                if apply:
                    document.publication_id = candidates[0].id
            elif len(candidates) > 1:
                ambiguous += 1
            else:
                unmatched += 1
        if apply:
            await session.commit()
    return {
        "scanned": scanned,
        "linked": linked,
        "ambiguous": ambiguous,
        "unmatched": unmatched,
        "applied": int(apply),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    print(asyncio.run(run(apply=args.apply, limit=args.limit)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
