from __future__ import annotations

import json
import os
import threading
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ManifestManager:
    """
    Thread-safe JSON manifest manager.

    Manifest structure:

    {
      "source": "bdu",
      "source_name": "...",
      "created_at": "...",
      "updated_at": "...",
      "statistics": {...},
      "documents": [...]
    }
    """

    def __init__(
        self,
        manifest_path: Path,
        *,
        source_key: str,
        source_name: str,
    ) -> None:
        self.manifest_path = manifest_path
        self.source_key = source_key
        self.source_name = source_name
        self.lock = threading.RLock()

        self.manifest_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.data = self._load_or_create()

    def _load_or_create(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            try:
                with self.manifest_path.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    payload = json.load(file)

                if isinstance(payload, dict):
                    payload.setdefault(
                        "source",
                        self.source_key,
                    )
                    payload.setdefault(
                        "source_name",
                        self.source_name,
                    )
                    payload.setdefault(
                        "documents",
                        [],
                    )
                    payload.setdefault(
                        "created_at",
                        utc_now(),
                    )
                    payload.setdefault(
                        "updated_at",
                        utc_now(),
                    )
                    payload.setdefault(
                        "statistics",
                        {},
                    )

                    self._refresh_statistics(payload)
                    return payload

            except (
                OSError,
                json.JSONDecodeError,
            ):
                backup_path = self.manifest_path.with_suffix(".corrupted.json")

                with suppress(OSError):
                    self.manifest_path.replace(backup_path)

        now = utc_now()

        return {
            "source": self.source_key,
            "source_name": self.source_name,
            "created_at": now,
            "updated_at": now,
            "statistics": {
                "total_found": 0,
                "discovered": 0,
                "downloading": 0,
                "downloaded": 0,
                "already_exists": 0,
                "failed": 0,
                "skipped": 0,
                "total_downloaded_bytes": 0,
            },
            "documents": [],
        }

    @staticmethod
    def build_document_id(
        external_id: str,
        document_url: str,
    ) -> str:
        return f"{external_id}::{document_url}"

    def _find_document_index(
        self,
        document_id: str,
    ) -> int | None:
        documents = self.data.get(
            "documents",
            [],
        )

        for index, document in enumerate(documents):
            if document.get("document_id") == document_id:
                return index

        return None

    def register_document(
        self,
        *,
        external_id: str,
        title: str | None,
        landing_url: str | None,
        document_url: str,
        filename: str | None = None,
        document_type: str | None = None,
        mime_type: str | None = None,
        expected_size_bytes: int | None = None,
        authors: list[str] | None = None,
        issued_date: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        document_id = self.build_document_id(
            external_id,
            document_url,
        )

        with self.lock:
            index = self._find_document_index(document_id)

            now = utc_now()

            if index is None:
                self.data["documents"].append(
                    {
                        "document_id": document_id,
                        "source": self.source_key,
                        "external_id": external_id,
                        "title": title,
                        "authors": authors or [],
                        "issued_date": issued_date,
                        "landing_url": landing_url,
                        "document_url": document_url,
                        "filename": filename,
                        "document_type": document_type,
                        "mime_type": mime_type,
                        "expected_size_bytes": (expected_size_bytes),
                        "downloaded_size_bytes": 0,
                        "progress_percent": 0.0,
                        "status": "discovered",
                        "local_path": None,
                        "partial_path": None,
                        "checksum_sha256": None,
                        "retry_count": 0,
                        "message": None,
                        "metadata": metadata or {},
                        "discovered_at": now,
                        "download_started_at": None,
                        "download_completed_at": None,
                        "last_attempt_at": None,
                        "updated_at": now,
                    }
                )

            else:
                document = self.data["documents"][index]

                document.update(
                    {
                        "title": (title or document.get("title")),
                        "landing_url": (landing_url or document.get("landing_url")),
                        "filename": (filename or document.get("filename")),
                        "document_type": (document_type or document.get("document_type")),
                        "mime_type": (mime_type or document.get("mime_type")),
                        "expected_size_bytes": (
                            expected_size_bytes or document.get("expected_size_bytes")
                        ),
                        "authors": (
                            authors
                            or document.get(
                                "authors",
                                [],
                            )
                        ),
                        "issued_date": (issued_date or document.get("issued_date")),
                        "updated_at": now,
                    }
                )

            self._save_locked()

        return document_id

    def update_document(
        self,
        document_id: str,
        **changes: Any,
    ) -> None:
        with self.lock:
            index = self._find_document_index(document_id)

            if index is None:
                return

            document = self.data["documents"][index]

            changes["updated_at"] = utc_now()

            document.update(changes)

            expected_size = document.get("expected_size_bytes")
            downloaded_size = document.get(
                "downloaded_size_bytes",
                0,
            )

            if (
                isinstance(expected_size, int)
                and expected_size > 0
                and isinstance(downloaded_size, int)
            ):
                progress = min(
                    100.0,
                    (downloaded_size / expected_size) * 100.0,
                )

                document["progress_percent"] = round(
                    progress,
                    2,
                )

            self._save_locked()

    def mark_downloading(
        self,
        document_id: str,
        *,
        partial_path: str,
        downloaded_size_bytes: int,
        expected_size_bytes: int | None,
        retry_count: int,
    ) -> None:
        now = utc_now()

        with self.lock:
            index = self._find_document_index(document_id)

            if index is None:
                return

            document = self.data["documents"][index]

            if not document.get("download_started_at"):
                document["download_started_at"] = now

            document.update(
                {
                    "status": "downloading",
                    "partial_path": partial_path,
                    "downloaded_size_bytes": (downloaded_size_bytes),
                    "expected_size_bytes": (
                        expected_size_bytes or document.get("expected_size_bytes")
                    ),
                    "retry_count": retry_count,
                    "last_attempt_at": now,
                    "message": None,
                    "updated_at": now,
                }
            )

            expected = document.get("expected_size_bytes")

            if isinstance(expected, int) and expected > 0:
                document["progress_percent"] = round(
                    min(
                        100.0,
                        downloaded_size_bytes / expected * 100.0,
                    ),
                    2,
                )

            self._save_locked()

    def mark_downloaded(
        self,
        document_id: str,
        *,
        local_path: str,
        document_type: str,
        mime_type: str | None,
        size_bytes: int,
        checksum_sha256: str,
    ) -> None:
        self.update_document(
            document_id,
            status="downloaded",
            local_path=local_path,
            partial_path=None,
            document_type=document_type,
            mime_type=mime_type,
            downloaded_size_bytes=size_bytes,
            expected_size_bytes=size_bytes,
            progress_percent=100.0,
            checksum_sha256=checksum_sha256,
            download_completed_at=utc_now(),
            message=None,
        )

    def mark_failed(
        self,
        document_id: str,
        *,
        message: str,
        downloaded_size_bytes: int = 0,
        partial_path: str | None = None,
        retry_count: int = 0,
    ) -> None:
        self.update_document(
            document_id,
            status="failed",
            message=message,
            downloaded_size_bytes=(downloaded_size_bytes),
            partial_path=partial_path,
            retry_count=retry_count,
        )

    def mark_skipped(
        self,
        document_id: str,
        *,
        message: str,
    ) -> None:
        self.update_document(
            document_id,
            status="skipped",
            message=message,
        )

    def mark_already_exists(
        self,
        document_id: str,
        *,
        local_path: str,
        size_bytes: int,
        checksum_sha256: str | None = None,
    ) -> None:
        self.update_document(
            document_id,
            status="already_exists",
            local_path=local_path,
            partial_path=None,
            downloaded_size_bytes=size_bytes,
            expected_size_bytes=size_bytes,
            progress_percent=100.0,
            checksum_sha256=checksum_sha256,
            download_completed_at=utc_now(),
            message=None,
        )

    def _refresh_statistics(
        self,
        payload: dict[str, Any] | None = None,
    ) -> None:
        target = payload or self.data
        documents = target.get(
            "documents",
            [],
        )

        statistics = {
            "total_found": len(documents),
            "discovered": 0,
            "downloading": 0,
            "downloaded": 0,
            "already_exists": 0,
            "failed": 0,
            "skipped": 0,
            "total_downloaded_bytes": 0,
        }

        for document in documents:
            status = document.get(
                "status",
                "discovered",
            )

            if status in statistics:
                statistics[status] += 1

            downloaded_size = document.get(
                "downloaded_size_bytes",
                0,
            )

            if isinstance(downloaded_size, int):
                statistics["total_downloaded_bytes"] += downloaded_size

        target["statistics"] = statistics

    def _save_locked(self) -> None:
        self._refresh_statistics()
        self.data["updated_at"] = utc_now()

        temporary_path = self.manifest_path.with_suffix(".json.tmp")

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                self.data,
                file,
                ensure_ascii=False,
                indent=2,
            )

            file.flush()
            os.fsync(file.fileno())

        temporary_path.replace(self.manifest_path)

    def save(self) -> None:
        with self.lock:
            self._save_locked()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return deepcopy(self.data)
