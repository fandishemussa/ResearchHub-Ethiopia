from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx"}
SUPPORTED_DOCUMENT_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def safe_filename(value: str, fallback: str = "document", max_length: int = 140) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r'[<>:/\\|?*\x00-\x1f"]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value[:max_length].rstrip(" .")
    return value or fallback


def url_filename(url: str) -> str | None:
    name = unquote(Path(urlparse(url).path).name).strip()
    return name or None


def normalize_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def extension_from_url(url: str) -> str:
    name = url_filename(url)
    return Path(name).suffix.lower() if name else ""


def detect_document_extension(
    *,
    url: str,
    content_type: str | None,
    first_bytes: bytes,
    filename: str | None = None,
) -> str | None:
    normalized = normalize_content_type(content_type)
    if normalized in SUPPORTED_DOCUMENT_MIME_TYPES:
        return SUPPORTED_DOCUMENT_MIME_TYPES[normalized]

    if first_bytes.startswith(b"%PDF-"):
        return ".pdf"
    if first_bytes.startswith(b"PK\x03\x04"):
        return ".docx"
    if first_bytes.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return ".doc"

    for value in (filename, url):
        if value:
            ext = Path(urlparse(value).path).suffix.lower()
            if ext in SUPPORTED_DOCUMENT_EXTENSIONS:
                return ext
    return None


def validate_document_signature(path: Path, extension: str) -> None:
    with path.open("rb") as fh:
        signature = fh.read(8)
    if extension == ".pdf" and not signature.startswith(b"%PDF-"):
        raise ValueError("Downloaded file does not have a valid PDF signature")
    if extension == ".docx" and not signature.startswith(b"PK\x03\x04"):
        raise ValueError("Downloaded file does not have a valid DOCX/ZIP signature")
    if extension == ".doc" and not signature.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise ValueError("Downloaded file does not have a valid legacy DOC signature")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_pdf(first_bytes: bytes, content_type: str | None) -> bool:
    """Backward-compatible PDF detector used by older tests/callers."""
    return (
        first_bytes.startswith(b"%PDF-")
        or normalize_content_type(content_type) == "application/pdf"
    )
