from __future__ import annotations

import argparse
import asyncio

from researchhub.infrastructure.persistence.session import (
    async_session_factory,
)
from sentence_transformers import SentenceTransformer
from sqlalchemy import text

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def vector_literal(
    values: list[float],
) -> str:
    return "[" + ",".join(f"{value:.10f}" for value in values) + "]"


async def run(query: str) -> None:
    model = SentenceTransformer(MODEL_NAME)

    embedding = model.encode(
        [query],
        normalize_embeddings=True,
    )[0]

    async with async_session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    rd.title,
                    rd.source,
                    rd.filename,
                    dc.page_start,
                    dc.page_end,
                    dc.content,
                    1 - (
                        dc.embedding
                            <=> CAST(:query_embedding AS vector)
                        ) AS similarity
                FROM document_chunks AS dc
                         JOIN research_documents AS rd
                              ON rd.id = dc.document_id
                WHERE dc.embedding IS NOT NULL
                ORDER BY dc.embedding
                    <=> CAST(:query_embedding AS vector)
                LIMIT 5
                """
            ),
            {
                "query_embedding": vector_literal(embedding.tolist()),
            },
        )

        for row in result.mappings():
            print("=" * 80)
            print(
                f"{row['title']} | "
                f"{row['source']} | "
                f"page {row['page_start']} | "
                f"similarity={row['similarity']:.4f}"
            )
            print(row["content"][:1000])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    args = parser.parse_args()

    asyncio.run(run(args.query))


if __name__ == "__main__":
    main()
