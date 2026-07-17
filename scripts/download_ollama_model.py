"""Resumably download an official Ollama model into an Ollama models volume.

This is a recovery utility for environments where Ollama's own Go registry
client returns EOF even though the registry is reachable. Every completed blob
is checked against the SHA-256 digest from the official registry manifest.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import httpx

REGISTRY = "https://registry.ollama.ai"
PRINT_LOCK = threading.Lock()
CONTENT_RANGE_PATTERN = re.compile(r"bytes (\d+)-(\d+)/(\d+)")


def report(message: str) -> None:
    with PRINT_LOCK:
        print(message, flush=True)


def retry_delay(attempt: int) -> int:
    return min(30, max(2, 2 ** min(attempt, 4)))


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_content_range(
    content_range: str | None,
    requested_start: int,
    requested_end: int,
    expected_total: int,
) -> None:
    match = CONTENT_RANGE_PATTERN.fullmatch((content_range or "").strip())
    if match is None:
        raise RuntimeError(f"missing or invalid Content-Range: {content_range!r}")
    actual_start, actual_end, actual_total = map(int, match.groups())
    if (actual_start, actual_end, actual_total) != (
        requested_start,
        requested_end,
        expected_total,
    ):
        raise RuntimeError(
            "unexpected Content-Range "
            f"{content_range!r}; expected bytes "
            f"{requested_start}-{requested_end}/{expected_total}"
        )


def fetch_manifest(repository: str, tag: str) -> tuple[bytes, dict[str, Any]]:
    attempt = 0
    while True:
        try:
            with httpx.Client(
                timeout=httpx.Timeout(300, connect=30), follow_redirects=True
            ) as client:
                response = client.get(f"{REGISTRY}/v2/{repository}/manifests/{tag}")
                response.raise_for_status()
                return response.content, response.json()
        except (httpx.HTTPError, ValueError) as exc:
            attempt += 1
            delay = retry_delay(attempt)
            report(f"manifest request failed ({type(exc).__name__}); retrying in {delay}s")
            time.sleep(delay)


def download_part(
    repository: str,
    digest: str,
    part: Path,
    start: int,
    end: int,
    total_size: int,
    index: int,
    worker_count: int,
) -> None:
    expected_size = end - start + 1
    attempt = 0
    while True:
        completed = part.stat().st_size if part.exists() else 0
        if completed > expected_size:
            part.unlink()
            completed = 0
        if completed == expected_size:
            report(f"part {index + 1}/{worker_count} complete")
            return

        try:
            requested_start = start + completed
            headers = {
                "Range": f"bytes={requested_start}-{end}",
                "Accept-Encoding": "identity",
            }
            with (
                httpx.Client(
                    timeout=httpx.Timeout(300, connect=30), follow_redirects=True
                ) as client,
                client.stream(
                    "GET", f"{REGISTRY}/v2/{repository}/blobs/{digest}", headers=headers
                ) as response,
            ):
                if response.status_code != 206:
                    raise RuntimeError(
                        f"part {index + 1}: expected HTTP 206, got {response.status_code}"
                    )
                validate_content_range(
                    response.headers.get("Content-Range"),
                    requested_start,
                    end,
                    total_size,
                )
                checkpoint = completed
                with part.open("ab" if completed else "wb") as handle:
                    for chunk in response.iter_raw(1024 * 1024):
                        handle.write(chunk)
                        completed += len(chunk)
                        if completed > expected_size:
                            raise RuntimeError(
                                f"part {index + 1}: response exceeded requested range"
                            )
                        if completed - checkpoint >= 64 * 1024 * 1024:
                            report(
                                f"part {index + 1}/{worker_count}: {completed / expected_size:.1%}"
                            )
                            checkpoint = completed
            attempt = 0
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            attempt += 1
            delay = retry_delay(attempt)
            report(
                f"part {index + 1}/{worker_count} interrupted "
                f"({type(exc).__name__}); retrying in {delay}s"
            )
            time.sleep(delay)


def download_small_blob(repository: str, descriptor: dict[str, Any], blobs: Path) -> None:
    digest = str(descriptor["digest"])
    expected_size = int(descriptor["size"])
    hex_digest = digest.split(":", 1)[1]
    destination = blobs / f"sha256-{hex_digest}"
    if destination.exists() and destination.stat().st_size == expected_size:
        if sha256_file(destination) == hex_digest:
            return
        report(f"discarding corrupt cached blob {destination.name}")
        destination.unlink()

    attempt = 0
    while True:
        try:
            with (
                httpx.Client(
                    timeout=httpx.Timeout(300, connect=30), follow_redirects=True
                ) as client,
                client.stream(
                    "GET",
                    f"{REGISTRY}/v2/{repository}/blobs/{digest}",
                    headers={"Accept-Encoding": "identity"},
                ) as response,
            ):
                response.raise_for_status()
                content = b"".join(response.iter_raw())
            if len(content) != expected_size or hashlib.sha256(content).hexdigest() != hex_digest:
                raise RuntimeError(f"validation failed for {digest}")
            temporary = destination.with_suffix(".manual")
            temporary.write_bytes(content)
            os.replace(temporary, destination)
            report(f"verified {destination.name}")
            return
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            attempt += 1
            delay = retry_delay(attempt)
            report(f"small blob interrupted ({type(exc).__name__}); retrying in {delay}s")
            time.sleep(delay)


def install(model: str, root: Path, workers: int) -> None:
    name, separator, tag = model.partition(":")
    if not separator:
        tag = "latest"
    repository = f"library/{name}"
    manifest_bytes, manifest = fetch_manifest(repository, tag)

    blobs = root / "blobs"
    manifest_path = root / "manifests" / "registry.ollama.ai" / "library" / name / tag
    blobs.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    model_layer = next(
        item
        for item in manifest["layers"]
        if item["mediaType"] == "application/vnd.ollama.image.model"
    )
    digest = str(model_layer["digest"])
    expected_size = int(model_layer["size"])
    hex_digest = digest.split(":", 1)[1]
    destination = blobs / f"sha256-{hex_digest}"
    segment_size = (expected_size + workers - 1) // workers
    ranges = [
        (
            index * segment_size,
            min(expected_size - 1, index * segment_size + segment_size - 1),
        )
        for index in range(workers)
    ]
    parts = [
        destination.with_name(f"{destination.name}.manual-v2-{start}-{end}.part")
        for start, end in ranges
    ]

    # Version-one parts were created without validating Content-Range and may
    # contain transparently decoded bytes. They are unsafe to resume.
    for stale in destination.parent.glob(f"{destination.name}.manual-part-*"):
        stale.unlink(missing_ok=True)
    destination.with_name(f"{destination.name}.manual-assembled").unlink(missing_ok=True)
    destination.with_name(f"{destination.name}-partial").unlink(missing_ok=True)

    destination_valid = (
        destination.exists()
        and destination.stat().st_size == expected_size
        and sha256_file(destination) == hex_digest
    )
    if destination.exists() and not destination_valid:
        report(f"discarding corrupt cached model blob {destination.name}")
        destination.unlink()

    if not destination_valid:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for index, (part, (start, end)) in enumerate(zip(parts, ranges, strict=True)):
                futures.append(
                    pool.submit(
                        download_part,
                        repository,
                        digest,
                        part,
                        start,
                        end,
                        expected_size,
                        index,
                        workers,
                    )
                )
            for future in futures:
                future.result()

        assembled = destination.with_name(f"{destination.name}.manual-assembled")
        hasher = hashlib.sha256()
        with assembled.open("wb") as output:
            for index, part in enumerate(parts):
                with part.open("rb") as source:
                    for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                        output.write(chunk)
                        hasher.update(chunk)
                report(f"assembled part {index + 1}/{workers}")

        actual_size = assembled.stat().st_size
        actual_digest = hasher.hexdigest()
        if actual_size != expected_size or actual_digest != hex_digest:
            assembled.unlink(missing_ok=True)
            for part in parts:
                part.unlink(missing_ok=True)
            raise RuntimeError(
                "assembled model verification failed; corrupt range cache removed "
                f"(size {actual_size}/{expected_size}, "
                f"sha256 {actual_digest}/{hex_digest})"
            )
        os.replace(assembled, destination)
        for part in parts:
            part.unlink(missing_ok=True)
        report(f"verified {destination.name}")

    for descriptor in [manifest["config"], *manifest["layers"]]:
        if descriptor["digest"] != digest:
            download_small_blob(repository, descriptor, blobs)

    temporary_manifest = manifest_path.with_suffix(".partial")
    temporary_manifest.write_bytes(manifest_bytes)
    os.replace(temporary_manifest, manifest_path)
    report(f"installed {model}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", default="qwen2.5:7b")
    parser.add_argument("--models-root", type=Path, default=Path("/root/.ollama/models"))
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    install(args.model, args.models_root, max(1, min(args.workers, 16)))


if __name__ == "__main__":
    main()
