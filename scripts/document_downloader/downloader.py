from __future__ import annotations

import json
import logging
import random
import time
from http.client import IncompleteRead
from pathlib import Path

import requests

from .bdu_handler import (
    discover_bdu_documents,
    iter_bdu_publications,
)
from .dspace7 import (
    discover_aau_documents,
    iter_aau_publications,
)
from .http_client import ResilientHttpClient
from .manifest import ManifestManager
from .models import (
    DownloadResult,
    DocumentCandidate,
    Publication,
    SourceConfig,
)
from .utils import (
    detect_document_extension,
    normalize_content_type,
    safe_filename,
    sha256_file,
    url_filename,
    validate_document_signature,
)
from .wku_handler import (
    discover_wku_documents,
    iter_wku_publications,
)

LOGGER = logging.getLogger(__name__)

DOWNLOAD_CHUNK_SIZE = 64 * 1024
MANIFEST_UPDATE_INTERVAL_BYTES = 1024 * 1024
MAX_DOWNLOAD_BACKOFF_SECONDS = 120

RETRYABLE_DOWNLOAD_ERRORS = (
    IncompleteRead,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ReadTimeout,
    requests.exceptions.Timeout,
    ConnectionResetError,
    BrokenPipeError,
    OSError,
)


class DocumentDownloadRunner:
    """
    Downloads PDF, DOC and DOCX research documents.

    The historical class name is preserved for compatibility.
    """

    def __init__(
        self,
        source: SourceConfig,
        output_dir: Path,
        *,
        timeout: float,
        retries: int,
        delay: float,
        verify_tls: bool,
        overwrite: bool,
        max_file_size_mb: int,
        all_pdfs: bool,
    ) -> None:
        self.source = source

        self.output_dir = output_dir / source.key
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.client = ResilientHttpClient(
            timeout=timeout,
            retries=retries,
            delay=delay,
            verify_tls=verify_tls,
        )

        self.download_retries = retries
        self.overwrite = overwrite
        self.max_bytes = (
            max_file_size_mb
            * 1024
            * 1024
        )

        # Preserve CLI compatibility with --all-pdfs.
        self.all_documents = all_pdfs

        self.manifest = ManifestManager(
            self.output_dir / "manifest.json",
            source_key=self.source.key,
            source_name=self.source.name,
        )

        self.completed = self._load_completed()

    def _load_completed(self) -> set[str]:
        """
        Load records that already have at least one completed document.
        """
        completed: set[str] = set()

        snapshot = self.manifest.snapshot()

        for document in snapshot.get(
            "documents",
            [],
        ):
            if document.get("status") not in {
                "downloaded",
                "already_exists",
            }:
                continue

            external_id = document.get(
                "external_id"
            )

            if external_id:
                completed.add(
                    str(external_id)
                )

        return completed

    def publications(
        self,
        max_records: int | None,
        from_date: str | None,
        set_spec: str | None,
        page_size: int,
    ):
        if self.source.kind in {
            "bdu_legacy_rest",
            "bdu_oai",
        }:
            return iter_bdu_publications(
                self.client,
                self.source,
                max_records=max_records,
                from_date=from_date,
                set_spec=set_spec,
                page_size=page_size,
            )

        if self.source.kind == "wku_rest":
            return iter_wku_publications(
                self.client,
                self.source,
                max_records=max_records,
                from_date=from_date,
                set_spec=set_spec,
                page_size=page_size,
            )

        if self.source.kind == "aau_dspace7":
            return iter_aau_publications(
                self.client,
                self.source,
                max_records=max_records,
                page_size=page_size,
            )

        raise ValueError(
            "Unsupported source kind: "
            f"{self.source.kind}"
        )

    def discover(self, publication: Publication,) -> list[DocumentCandidate]:
        if self.source.kind in {
            "bdu_legacy_rest",
            "bdu_oai",
        }:
            return discover_bdu_documents(
                self.client,
                self.source,
                publication,
            )

        if self.source.kind == "wku_rest":
            return discover_wku_documents(
                self.client,
                self.source,
                publication,
            )

        if self.source.kind == "aau_dspace7":
            if not publication.item_uuid:
                LOGGER.warning(
                    "AAU publication %s has no item UUID",
                    publication.external_id,
                )
                return []

            return discover_aau_documents(
                self.client,
                self.source,
                publication.item_uuid,
            )

        return []

    def _base_target_path(
        self,
        publication: Publication,
        candidate: DocumentCandidate,
        index: int,
        extension: str,
    ) -> Path:
        source_name = (
            candidate.filename
            or url_filename(candidate.url)
            or f"document{extension}"
        )

        external_id_suffix = (
            publication.external_id
            .rsplit("/", 1)[-1]
            .rsplit(":", 1)[-1]
        )

        id_part = safe_filename(
            external_id_suffix,
            "record",
            40,
        )

        title_part = safe_filename(
            publication.title
            or Path(source_name).stem,
            "document",
            100,
        )

        suffix = (
            f"_{index}"
            if index > 1
            else ""
        )

        type_directory = (
            self.output_dir
            / extension.lstrip(".")
        )

        type_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        return (
            type_directory
            / (
                f"{id_part}_"
                f"{title_part}"
                f"{suffix}"
                f"{extension}"
            )
        )

    def _register_candidate(
        self,
        publication: Publication,
        candidate: DocumentCandidate,
        index: int,
        guessed_extension: str | None,
    ) -> str:
        authors = getattr(
            publication,
            "authors",
            [],
        )

        issued_date = getattr(
            publication,
            "issued_date",
            None,
        )

        return self.manifest.register_document(
            external_id=publication.external_id,
            title=publication.title,
            landing_url=publication.landing_url,
            document_url=candidate.url,
            filename=candidate.filename,
            document_type=(
                guessed_extension.lstrip(".")
                if guessed_extension
                else None
            ),
            mime_type=candidate.mime_type,
            expected_size_bytes=(
                candidate.size_bytes
            ),
            authors=authors or [],
            issued_date=issued_date,
            metadata={
                "candidate_index": index,
                "repository_kind": (
                    self.source.kind
                ),
            },
        )

    def _download_candidate(
        self,
        publication: Publication,
        candidate: DocumentCandidate,
        index: int,
    ) -> DownloadResult:
        guessed_extension = (
            detect_document_extension(
                url=candidate.url,
                content_type=candidate.mime_type,
                first_bytes=b"",
                filename=candidate.filename,
            )
        )

        document_id = self._register_candidate(
            publication,
            candidate,
            index,
            guessed_extension,
        )

        provisional_extension = (
            guessed_extension
            or ".bin"
        )

        provisional_target = (
            self._base_target_path(
                publication,
                candidate,
                index,
                provisional_extension,
            )
        )

        part_path = (
            provisional_target.with_suffix(
                provisional_target.suffix
                + ".part"
            )
        )

        last_error: Exception | None = None
        expected_total: int | None = (
            candidate.size_bytes
        )

        for attempt in range(
            1,
            self.download_retries + 1,
        ):
            response = None

            try:
                saved_bytes = (
                    part_path.stat().st_size
                    if part_path.exists()
                    else 0
                )

                headers = {
                    "Accept": (
                        "application/pdf,"
                        "application/msword,"
                        "application/vnd."
                        "openxmlformats-officedocument."
                        "wordprocessingml.document,"
                        "application/octet-stream,"
                        "*/*;q=0.5"
                    ),
                    "Accept-Encoding": "identity",
                    "Connection": "keep-alive",
                }

                if saved_bytes > 0:
                    headers["Range"] = (
                        f"bytes={saved_bytes}-"
                    )

                    LOGGER.info(
                        "Resuming %s from byte %s",
                        candidate.url,
                        saved_bytes,
                    )

                self.manifest.mark_downloading(
                    document_id,
                    partial_path=str(part_path),
                    downloaded_size_bytes=(
                        saved_bytes
                    ),
                    expected_size_bytes=(
                        expected_total
                    ),
                    retry_count=attempt - 1,
                )

                response = self.client.stream(
                    candidate.url,
                    headers=headers,
                    timeout=(
                        30.0,
                        self.client.read_timeout,
                    ),
                )

                status_code = (
                    response.status_code
                )

                if saved_bytes > 0:
                    if status_code == 206:
                        content_range = (
                            response.headers.get(
                                "Content-Range",
                                "",
                            )
                        )

                        expected_prefix = (
                            f"bytes {saved_bytes}-"
                        )

                        if (
                            content_range
                            and not content_range.startswith(
                                expected_prefix
                            )
                        ):
                            LOGGER.warning(
                                "Unexpected Content-Range "
                                "%r for %s; restarting",
                                content_range,
                                candidate.url,
                            )

                            response.close()
                            response = None

                            part_path.unlink(
                                missing_ok=True
                            )

                            saved_bytes = 0
                            expected_total = (
                                candidate.size_bytes
                            )

                            continue

                    elif status_code == 416:
                        LOGGER.warning(
                            "Server rejected resume "
                            "position for %s; restarting",
                            candidate.url,
                        )

                        response.close()
                        response = None

                        part_path.unlink(
                            missing_ok=True
                        )

                        saved_bytes = 0
                        expected_total = (
                            candidate.size_bytes
                        )

                        continue

                    else:
                        LOGGER.warning(
                            "Server ignored Range request "
                            "for %s; restarting from zero",
                            candidate.url,
                        )

                        part_path.unlink(
                            missing_ok=True
                        )

                        saved_bytes = 0

                declared_length = (
                    response.headers.get(
                        "Content-Length"
                    )
                )

                if (
                    declared_length
                    and declared_length.isdigit()
                ):
                    response_bytes = int(
                        declared_length
                    )

                    expected_total = (
                        saved_bytes
                        + response_bytes
                        if status_code == 206
                        else response_bytes
                    )

                    if (
                        expected_total
                        > self.max_bytes
                    ):
                        message = (
                            "File exceeds maximum size "
                            f"of {self.max_bytes} bytes"
                        )

                        self.manifest.mark_skipped(
                            document_id,
                            message=message,
                        )

                        return DownloadResult(
                            self.source.key,
                            publication.external_id,
                            publication.title,
                            publication.landing_url,
                            candidate.url,
                            None,
                            "skipped",
                            document_type=(
                                guessed_extension
                                .lstrip(".")
                                if guessed_extension
                                else None
                            ),
                            mime_type=(
                                candidate.mime_type
                            ),
                            size_bytes=(
                                expected_total
                            ),
                            message=message,
                        )

                append_mode = (
                    saved_bytes > 0
                    and status_code == 206
                )

                file_mode = (
                    "ab"
                    if append_mode
                    else "wb"
                )

                total_written = (
                    saved_bytes
                    if append_mode
                    else 0
                )

                last_manifest_update = (
                    total_written
                )

                first_bytes = b""

                self.manifest.mark_downloading(
                    document_id,
                    partial_path=str(part_path),
                    downloaded_size_bytes=(
                        total_written
                    ),
                    expected_size_bytes=(
                        expected_total
                    ),
                    retry_count=attempt - 1,
                )

                with part_path.open(
                    file_mode
                ) as output_file:
                    for chunk in (
                        response.iter_content(
                            chunk_size=(
                                DOWNLOAD_CHUNK_SIZE
                            )
                        )
                    ):
                        if not chunk:
                            continue

                        if not first_bytes:
                            first_bytes = chunk[:16]

                        output_file.write(chunk)

                        total_written += len(
                            chunk
                        )

                        if (
                            total_written
                            > self.max_bytes
                        ):
                            raise ValueError(
                                "File exceeds maximum "
                                f"size of "
                                f"{self.max_bytes} bytes"
                            )

                        progress_since_update = (
                            total_written
                            - last_manifest_update
                        )

                        if (
                            progress_since_update
                            >= MANIFEST_UPDATE_INTERVAL_BYTES
                        ):
                            output_file.flush()

                            self.manifest.mark_downloading(
                                document_id,
                                partial_path=(
                                    str(part_path)
                                ),
                                downloaded_size_bytes=(
                                    total_written
                                ),
                                expected_size_bytes=(
                                    expected_total
                                ),
                                retry_count=(
                                    attempt - 1
                                ),
                            )

                            last_manifest_update = (
                                total_written
                            )

                            if expected_total:
                                percent = min(
                                    100.0,
                                    (
                                        total_written
                                        / expected_total
                                    )
                                    * 100.0,
                                )

                                LOGGER.info(
                                    "Downloading %s: "
                                    "%.2f MB / %.2f MB "
                                    "(%.2f%%)",
                                    candidate.url,
                                    total_written
                                    / (1024 * 1024),
                                    expected_total
                                    / (1024 * 1024),
                                    percent,
                                )
                            else:
                                LOGGER.info(
                                    "Downloading %s: "
                                    "%.2f MB saved",
                                    candidate.url,
                                    total_written
                                    / (1024 * 1024),
                                )

                    output_file.flush()

                self.manifest.mark_downloading(
                    document_id,
                    partial_path=str(part_path),
                    downloaded_size_bytes=(
                        total_written
                    ),
                    expected_size_bytes=(
                        expected_total
                    ),
                    retry_count=attempt - 1,
                )

                if append_mode:
                    with part_path.open(
                        "rb"
                    ) as file_handle:
                        first_bytes = (
                            file_handle.read(16)
                        )

                content_type = (
                    normalize_content_type(
                        response.headers.get(
                            "Content-Type"
                        )
                    )
                )

                extension = (
                    detect_document_extension(
                        url=candidate.url,
                        content_type=(
                            content_type
                        ),
                        first_bytes=first_bytes,
                        filename=(
                            candidate.filename
                        ),
                    )
                )

                if extension is None:
                    raise ValueError(
                        "Downloaded content is not "
                        "a supported PDF, DOC, or "
                        "DOCX document "
                        f"(Content-Type="
                        f"{content_type!r})"
                    )

                target = self._base_target_path(
                    publication,
                    candidate,
                    index,
                    extension,
                )

                if (
                    target.exists()
                    and not self.overwrite
                ):
                    part_path.unlink(
                        missing_ok=True
                    )

                    checksum = sha256_file(
                        target
                    )

                    self.manifest.mark_already_exists(
                        document_id,
                        local_path=str(target),
                        size_bytes=(
                            target.stat().st_size
                        ),
                        checksum_sha256=(
                            checksum
                        ),
                    )

                    self.completed.add(
                        publication.external_id
                    )

                    return DownloadResult(
                        self.source.key,
                        publication.external_id,
                        publication.title,
                        publication.landing_url,
                        candidate.url,
                        str(target),
                        "already_exists",
                        extension.lstrip("."),
                        (
                            content_type
                            or candidate.mime_type
                        ),
                        target.stat().st_size,
                        checksum,
                    )

                validate_document_signature(
                    part_path,
                    extension,
                )

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                part_path.replace(target)

                file_size = (
                    target.stat().st_size
                )

                checksum = sha256_file(
                    target
                )

                self.manifest.mark_downloaded(
                    document_id,
                    local_path=str(target),
                    document_type=(
                        extension.lstrip(".")
                    ),
                    mime_type=(
                        content_type
                        or candidate.mime_type
                    ),
                    size_bytes=file_size,
                    checksum_sha256=checksum,
                )

                self.completed.add(
                    publication.external_id
                )

                return DownloadResult(
                    self.source.key,
                    publication.external_id,
                    publication.title,
                    publication.landing_url,
                    candidate.url,
                    str(target),
                    "downloaded",
                    extension.lstrip("."),
                    (
                        content_type
                        or candidate.mime_type
                    ),
                    file_size,
                    checksum,
                )

            except RETRYABLE_DOWNLOAD_ERRORS as exc:
                last_error = exc

                saved_bytes = (
                    part_path.stat().st_size
                    if part_path.exists()
                    else 0
                )

                LOGGER.warning(
                    "Interrupted download for %s "
                    "(attempt %s/%s, "
                    "saved=%s bytes): %s",
                    candidate.url,
                    attempt,
                    self.download_retries,
                    saved_bytes,
                    exc,
                )

                self.manifest.mark_downloading(
                    document_id,
                    partial_path=str(part_path),
                    downloaded_size_bytes=(
                        saved_bytes
                    ),
                    expected_size_bytes=(
                        expected_total
                    ),
                    retry_count=attempt,
                )

                if (
                    attempt
                    >= self.download_retries
                ):
                    break

                wait = min(
                    2 ** attempt,
                    MAX_DOWNLOAD_BACKOFF_SECONDS,
                )

                wait += random.uniform(
                    0,
                    2,
                )

                LOGGER.info(
                    "Waiting %.1f seconds before "
                    "resuming download",
                    wait,
                )

                time.sleep(wait)

            except ValueError as exc:
                last_error = exc

                saved_bytes = (
                    part_path.stat().st_size
                    if part_path.exists()
                    else 0
                )

                message = str(exc)

                if (
                    "exceeds maximum size"
                    in message.lower()
                ):
                    self.manifest.mark_skipped(
                        document_id,
                        message=message,
                    )
                else:
                    self.manifest.mark_failed(
                        document_id,
                        message=message,
                        downloaded_size_bytes=(
                            saved_bytes
                        ),
                        partial_path=(
                            str(part_path)
                            if part_path.exists()
                            else None
                        ),
                        retry_count=attempt,
                    )

                break

            except Exception as exc:
                last_error = exc

                saved_bytes = (
                    part_path.stat().st_size
                    if part_path.exists()
                    else 0
                )

                self.manifest.mark_failed(
                    document_id,
                    message=str(exc),
                    downloaded_size_bytes=(
                        saved_bytes
                    ),
                    partial_path=(
                        str(part_path)
                        if part_path.exists()
                        else None
                    ),
                    retry_count=attempt,
                )

                break

            finally:
                if response is not None:
                    response.close()

        saved_bytes = (
            part_path.stat().st_size
            if part_path.exists()
            else 0
        )

        failure_message = (
            str(last_error)
            if last_error
            else "Download failed"
        )

        self.manifest.mark_failed(
            document_id,
            message=failure_message,
            downloaded_size_bytes=(
                saved_bytes
            ),
            partial_path=(
                str(part_path)
                if part_path.exists()
                else None
            ),
            retry_count=(
                self.download_retries
            ),
        )

        return DownloadResult(
            self.source.key,
            publication.external_id,
            publication.title,
            publication.landing_url,
            candidate.url,
            None,
            "failed",
            (
                guessed_extension.lstrip(".")
                if guessed_extension
                else None
            ),
            candidate.mime_type,
            saved_bytes,
            message=failure_message,
        )

    def run(
        self,
        *,
        max_records: int | None,
        max_downloads: int | None,
        from_date: str | None,
        set_spec: str | None,
        page_size: int,
        resume: bool,
    ) -> list[DownloadResult]:
        results: list[DownloadResult] = []
        successful_downloads = 0

        try:
            publications = self.publications(
                max_records,
                from_date,
                set_spec,
                page_size,
            )

            for position, publication in enumerate(
                publications,
                start=1,
            ):
                LOGGER.info(
                    "[%s] %s",
                    position,
                    (
                        publication.title
                        or publication.external_id
                    ),
                )

                if (
                    resume
                    and publication.external_id
                    in self.completed
                ):
                    LOGGER.info(
                        "Skipping completed record %s",
                        publication.external_id,
                    )
                    continue

                try:
                    candidates = self.discover(
                        publication
                    )

                except Exception as exc:
                    LOGGER.exception(
                        "Document discovery failed "
                        "for %s",
                        publication.external_id,
                    )

                    result = DownloadResult(
                        self.source.key,
                        publication.external_id,
                        publication.title,
                        publication.landing_url,
                        None,
                        None,
                        "failed",
                        message=(
                            "Document discovery "
                            f"failed: {exc}"
                        ),
                    )

                    results.append(result)
                    continue

                if not candidates:
                    LOGGER.warning(
                        "No public PDF, DOC, or "
                        "DOCX document found for %s",
                        publication.external_id,
                    )

                    result = DownloadResult(
                        self.source.key,
                        publication.external_id,
                        publication.title,
                        publication.landing_url,
                        None,
                        None,
                        "not_found",
                        message=(
                            "No public PDF, DOC, "
                            "or DOCX link discovered"
                        ),
                    )

                    results.append(result)
                    continue

                selected_candidates = (
                    candidates
                    if self.all_documents
                    else candidates[:1]
                )

                for index, candidate in enumerate(
                    selected_candidates,
                    start=1,
                ):
                    result = (
                        self._download_candidate(
                            publication,
                            candidate,
                            index,
                        )
                    )

                    results.append(result)

                    if result.status in {
                        "downloaded",
                        "already_exists",
                    }:
                        successful_downloads += 1

                        if (
                            max_downloads
                            is not None
                            and successful_downloads
                            >= max_downloads
                        ):
                            return results

            return results

        finally:
            self.manifest.save()
            self.close()

    def close(self) -> None:
        self.client.close()


def write_summary(
    output_dir: Path,
    source_key: str,
    results: list[DownloadResult],
) -> Path:
    counts: dict[str, int] = {}
    document_types: dict[str, int] = {}

    total_downloaded_bytes = 0

    for result in results:
        counts[result.status] = (
            counts.get(
                result.status,
                0,
            )
            + 1
        )

        if (
            result.status
            in {
                "downloaded",
                "already_exists",
            }
            and result.document_type
        ):
            document_types[
                result.document_type
            ] = (
                document_types.get(
                    result.document_type,
                    0,
                )
                + 1
            )

        if (
            result.status
            in {
                "downloaded",
                "already_exists",
            }
            and isinstance(
                result.size_bytes,
                int,
            )
        ):
            total_downloaded_bytes += (
                result.size_bytes
            )

    summary = {
        "source": source_key,
        "total_results": len(results),
        "counts": counts,
        "document_types": document_types,
        "total_downloaded_bytes": (
            total_downloaded_bytes
        ),
        "manifest": "manifest.json",
    }

    source_directory = (
        output_dir / source_key
    )

    source_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        source_directory
        / "summary.json"
    )

    path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path