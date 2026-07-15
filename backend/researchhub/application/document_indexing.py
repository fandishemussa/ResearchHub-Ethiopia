from __future__ import annotations

import hashlib
from pathlib import Path

from researchhub_ai.embeddings import get_embedding_service

from researchhub.application.document_chunking import chunk_pages
from researchhub.application.document_extraction import extract_document


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while block := file.read(1024 * 1024):
            digest.update(block)

    return digest.hexdigest()


def extract_and_embed(path: Path) -> dict:
    pages = extract_document(path)
    chunks = chunk_pages(pages)

    embedding_service = get_embedding_service()

    texts = [
        chunk.content
        for chunk in chunks
    ]

    embeddings = embedding_service.encode_documents(
        texts,
        batch_size=16,
    )

    return {
        "path": str(path),
        "checksum_sha256": calculate_sha256(path),
        "page_count": len(pages),
        "embedding_model": (
            embedding_service.get_model_name()
        ),
        "chunks": [
            {
                "chunk_index": chunk.chunk_index,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "content": chunk.content,
                "embedding": embedding,
            }
            for chunk, embedding in zip(
                chunks,
                embeddings,
                strict=True,
            )
        ],
    }