from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fitz
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

SUPPORTED_EXTENSIONS = {
    ".pdf",
}


@dataclass(slots=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(slots=True)
class DocumentChunkData:
    chunk_index: int
    page_start: int
    page_end: int
    content: str


_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    global _embedding_model

    if _embedding_model is None:
        LOGGER.info(
            "Loading embedding model: %s",
            EMBEDDING_MODEL,
        )

        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)

    return _embedding_model


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while block := file.read(1024 * 1024):
            digest.update(block)

    return digest.hexdigest()


def repair_text_encoding(value: str) -> str:
    """Repair common mojibake sequences produced by PDF extraction."""

    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "–",
        "â€”": "—",
        "â€¦": "…",
        "Â ": " ",
        "Â": "",
    }

    repaired = value
    for broken, correct in replacements.items():
        repaired = repaired.replace(broken, correct)

    return repaired


def clean_document_title(path: Path, title: str | None = None) -> str:
    """Return a readable title without downloader UUID or numeric prefixes."""

    value = (title or path.stem).strip()
    value = re.sub(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}_",
        "",
        value,
    )
    value = re.sub(r"^\d+_", "", value)
    value = re.sub(r"\s+", " ", value).strip(" _-")
    return value or "Untitled research document"


def clean_text(value: str) -> str:
    value = repair_text_encoding(value)
    value = value.replace("\x00", " ")
    value = value.replace("\r\n", "\n")
    value = value.replace("\r", "\n")

    lines = [line.strip() for line in value.splitlines()]

    cleaned_lines: list[str] = []

    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        cleaned_lines.append(" ".join(line.split()))

    return "\n".join(cleaned_lines).strip()


def extract_pdf_pages(path: Path) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []

    with fitz.open(path) as document:
        for page_number, page in enumerate(
            document,
            start=1,
        ):
            raw_text = page.get_text(
                "text",
                sort=True,
            )

            cleaned = clean_text(raw_text)

            if not cleaned:
                continue

            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    text=cleaned,
                )
            )

    return pages


def chunk_pages(
    pages: list[ExtractedPage],
    *,
    chunk_size: int = 3200,
    overlap: int = 400,
) -> list[DocumentChunkData]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[DocumentChunkData] = []
    chunk_index = 0

    for page in pages:
        text_value = page.text.strip()

        if not text_value:
            continue

        start = 0

        while start < len(text_value):
            end = min(
                start + chunk_size,
                len(text_value),
            )

            if end < len(text_value):
                paragraph_break = text_value.rfind(
                    "\n\n",
                    start,
                    end,
                )

                sentence_break = text_value.rfind(
                    ". ",
                    start,
                    end,
                )

                selected_break = max(
                    paragraph_break,
                    sentence_break,
                )

                if selected_break > start + chunk_size // 2:
                    end = selected_break + 1

            content = text_value[start:end].strip()

            if content:
                chunks.append(
                    DocumentChunkData(
                        chunk_index=chunk_index,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        content=content,
                    )
                )

                chunk_index += 1

            if end >= len(text_value):
                break

            start = max(
                end - overlap,
                start + 1,
            )

    return chunks


def estimate_token_count(content: str) -> int:
    return max(
        1,
        round(len(content.split()) * 1.3),
    )


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.10f}" for value in vector) + "]"


async def index_pdf(
    session: AsyncSession,
    *,
    path: Path,
    source: str,
    publication_id: uuid.UUID | None = None,
    title: str | None = None,
    external_id: str | None = None,
    document_url: str | None = None,
    landing_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = path.resolve()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    checksum = sha256_file(path)

    existing_result = await session.execute(
        text(
            """
            SELECT id, checksum_sha256, extraction_status
            FROM research_documents
            WHERE local_path = :local_path
            """
        ),
        {
            "local_path": str(path),
        },
    )

    existing = existing_result.mappings().first()

    if (
        existing
        and existing["checksum_sha256"] == checksum
        and existing["extraction_status"] == "indexed"
    ):
        if publication_id:
            await session.execute(
                text(
                    "UPDATE research_documents SET publication_id = :publication_id "
                    "WHERE id = :document_id AND publication_id IS NULL"
                ),
                {"publication_id": publication_id, "document_id": existing["id"]},
            )
            await session.commit()
        return {
            "document_id": str(existing["id"]),
            "status": "already_indexed",
            "path": str(path),
        }

    document_id = existing["id"] if existing else uuid.uuid4()

    try:
        await session.execute(
            text(
                """
                INSERT INTO research_documents (
                    id,
                    publication_id,
                    source,
                    external_id,
                    title,
                    local_path,
                    document_url,
                    landing_url,
                    filename,
                    mime_type,
                    file_extension,
                    checksum_sha256,
                    file_size_bytes,
                    extraction_status,
                    metadata_json,
                    downloaded_at,
                    created_at,
                    updated_at
                )
                VALUES (
                           :id,
                           :publication_id,
                           :source,
                           :external_id,
                           :title,
                           :local_path,
                           :document_url,
                           :landing_url,
                           :filename,
                           :mime_type,
                           :file_extension,
                           :checksum_sha256,
                           :file_size_bytes,
                           'extracting',
                           CAST(:metadata_json AS jsonb),
                           :downloaded_at,
                           now(),
                           now()
                       )
                ON CONFLICT (local_path)
                    DO UPDATE SET
                                  source = EXCLUDED.source,
                                  publication_id = COALESCE(EXCLUDED.publication_id, research_documents.publication_id),
                                  external_id = EXCLUDED.external_id,
                                  title = EXCLUDED.title,
                                  document_url = EXCLUDED.document_url,
                                  landing_url = EXCLUDED.landing_url,
                                  filename = EXCLUDED.filename,
                                  mime_type = EXCLUDED.mime_type,
                                  file_extension = EXCLUDED.file_extension,
                                  checksum_sha256 = EXCLUDED.checksum_sha256,
                                  file_size_bytes = EXCLUDED.file_size_bytes,
                                  extraction_status = 'extracting',
                                  extraction_error = NULL,
                                  metadata_json = EXCLUDED.metadata_json,
                                  updated_at = now()
                """
            ),
            {
                "id": document_id,
                "publication_id": publication_id,
                "source": source,
                "external_id": external_id,
                "title": clean_document_title(path, title),
                "local_path": str(path),
                "document_url": document_url,
                "landing_url": landing_url,
                "filename": path.name,
                "mime_type": "application/pdf",
                "file_extension": path.suffix.lower(),
                "checksum_sha256": checksum,
                "file_size_bytes": path.stat().st_size,
                "metadata_json": json.dumps(metadata or {}),
                "downloaded_at": datetime.now(UTC),
            },
        )

        await session.commit()

        pages = extract_pdf_pages(path)
        chunks = chunk_pages(pages)

        if not pages:
            raise RuntimeError("No extractable text found in PDF")

        if not chunks:
            raise RuntimeError("Text extraction produced no chunks")

        await session.execute(
            text(
                "UPDATE research_documents SET extraction_status = 'chunking', "
                "last_attempted_at = now(), updated_at = now() WHERE id = :document_id"
            ),
            {"document_id": document_id},
        )
        await session.commit()

        model = get_embedding_model()

        chunk_texts = [chunk.content for chunk in chunks]

        await session.execute(
            text(
                "UPDATE research_documents SET extraction_status = 'embedding', "
                "updated_at = now() WHERE id = :document_id"
            ),
            {"document_id": document_id},
        )
        await session.commit()

        embeddings = model.encode(
            chunk_texts,
            batch_size=16,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        await session.execute(
            text(
                """
                DELETE FROM document_chunks
                WHERE document_id = :document_id
                """
            ),
            {
                "document_id": document_id,
            },
        )

        for chunk, embedding in zip(
            chunks,
            embeddings,
            strict=True,
        ):
            content_hash = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()

            await session.execute(
                text(
                    """
                    INSERT INTO document_chunks (
                        id,
                        document_id,
                        chunk_index,
                        page_start,
                        page_end,
                        content,
                        character_count,
                        token_count,
                        embedding,
                        embedding_model,
                        content_hash,
                        chunk_metadata,
                        embedded_at,
                        created_at
                    )
                    VALUES (
                               :id,
                               :document_id,
                               :chunk_index,
                               :page_start,
                               :page_end,
                               :content,
                               :character_count,
                               :token_count,
                               CAST(:embedding AS vector),
                               :embedding_model,
                               :content_hash,
                               '{}'::jsonb,
                               :embedded_at,
                               now()
                           )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "document_id": document_id,
                    "chunk_index": chunk.chunk_index,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "content": chunk.content,
                    "character_count": len(chunk.content),
                    "token_count": estimate_token_count(chunk.content),
                    "embedding": vector_literal(embedding.tolist()),
                    "embedding_model": EMBEDDING_MODEL,
                    "content_hash": content_hash,
                    "embedded_at": datetime.now(UTC),
                },
            )

        total_characters = sum(len(page.text) for page in pages)

        now = datetime.now(UTC)

        await session.execute(
            text(
                """
                UPDATE research_documents
                SET page_count = :page_count,
                    character_count = :character_count,
                    chunk_count = :chunk_count,
                    extraction_status = 'indexed',
                    extraction_error = NULL,
                    processing_error_code = NULL,
                    technical_error = NULL,
                    extracted_at = :now,
                    indexed_at = :now,
                    updated_at = :now
                WHERE id = :document_id
                """
            ),
            {
                "page_count": len(pages),
                "character_count": total_characters,
                "chunk_count": len(chunks),
                "now": now,
                "document_id": document_id,
            },
        )

        if publication_id:
            await session.execute(
                text(
                    "UPDATE publication_summaries SET is_stale = true "
                    "WHERE publication_id = :publication_id"
                ),
                {"publication_id": publication_id},
            )

        await session.commit()

        return {
            "document_id": str(document_id),
            "status": "indexed",
            "path": str(path),
            "page_count": len(pages),
            "chunk_count": len(chunks),
            "character_count": total_characters,
            "embedding_model": EMBEDDING_MODEL,
        }

    except Exception as exc:
        await session.rollback()

        await session.execute(
            text(
                """
                UPDATE research_documents
                SET extraction_status = 'failed',
                    extraction_error = :error,
                    processing_error_code = :error_code,
                    technical_error = :technical_error,
                    retry_count = retry_count + 1,
                    last_attempted_at = now(),
                    updated_at = now()
                WHERE local_path = :local_path
                """
            ),
            {
                "error": str(exc)[:5000],
                "error_code": type(exc).__name__[:80],
                "technical_error": repr(exc)[:5000],
                "local_path": str(path),
            },
        )

        await session.commit()
        raise
