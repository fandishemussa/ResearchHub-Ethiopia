from pathlib import Path

import pytest
from download_ollama_model import sha256_file, validate_content_range


def test_validate_content_range_accepts_the_exact_requested_range() -> None:
    validate_content_range("bytes 10-19/100", 10, 19, 100)


@pytest.mark.parametrize(
    "header",
    [None, "", "bytes 0-9/*", "bytes 0-9/99", "bytes 1-10/100"],
)
def test_validate_content_range_rejects_unsafe_responses(header: str | None) -> None:
    with pytest.raises(RuntimeError):
        validate_content_range(header, 0, 9, 100)


def test_sha256_file_hashes_the_raw_file_bytes(tmp_path: Path) -> None:
    blob = tmp_path / "blob"
    blob.write_bytes(b"researchhub")

    assert sha256_file(blob) == (
        "5dea4da181cdb2864f9571a90917b76008bcfbd1a8f3a2f00e6137aad3604818"
    )
