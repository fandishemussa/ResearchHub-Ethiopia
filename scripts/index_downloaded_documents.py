from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from researchhub.application.document_indexer import (
    index_pdf,
)
from researchhub.infrastructure.persistence.session import (
    async_session_factory,
)

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Extract and index downloaded research PDFs into PostgreSQL and pgvector.")
    )

    parser.add_argument(
        "--input-dir",
        default="/app/data/research-documents",
    )
    parser.add_argument(
        "--source",
        choices=[
            "aau",
            "wku",
            "bdu",
            "all",
        ],
        default="all",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args()


def load_manifest(
    source_directory: Path,
) -> dict[str, dict[str, Any]]:
    manifest_path = source_directory / "manifest.json"

    if not manifest_path.exists():
        return {}

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning(
            "Could not read manifest %s: %s",
            manifest_path,
            exc,
        )
        return {}

    if isinstance(payload, dict):
        records = (
            payload.get("documents") or payload.get("items") or payload.get("entries") or payload
        )
    else:
        records = payload

    by_path: dict[str, dict[str, Any]] = {}

    if isinstance(records, dict):
        iterable = records.values()
    elif isinstance(records, list):
        iterable = records
    else:
        return {}

    for record in iterable:
        if not isinstance(record, dict):
            continue

        path_value = record.get("local_path") or record.get("path") or record.get("final_path")

        if path_value:
            by_path[Path(str(path_value)).name] = record

    return by_path


async def run() -> int:
    args = parse_args()

    root = Path(args.input_dir)

    sources = ["aau", "wku", "bdu"] if args.source == "all" else [args.source]

    indexed = 0
    skipped = 0
    failed = 0

    for source in sources:
        source_directory = root / source

        if not source_directory.exists():
            LOGGER.warning(
                "Source directory not found: %s",
                source_directory,
            )
            continue

        manifest = load_manifest(source_directory)

        pdf_paths = sorted(path for path in source_directory.rglob("*.pdf") if path.is_file())

        for path in pdf_paths:
            if args.limit is not None and indexed >= args.limit:
                print(
                    {
                        "indexed": indexed,
                        "skipped": skipped,
                        "failed": failed,
                    }
                )
                return 0

            record = manifest.get(
                path.name,
                {},
            )

            try:
                async with async_session_factory() as session:
                    result = await index_pdf(
                        session,
                        path=path,
                        source=source,
                        title=record.get("title"),
                        external_id=(record.get("external_id") or record.get("publication_id")),
                        document_url=record.get("document_url"),
                        landing_url=record.get("landing_url"),
                        metadata=record,
                    )

                if result["status"] == "already_indexed":
                    skipped += 1
                else:
                    indexed += 1

                print(result)

            except Exception as exc:
                failed += 1

                LOGGER.exception(
                    "Failed to index %s: %s",
                    path,
                    exc,
                )

                if not args.continue_on_error:
                    raise

    print(
        {
            "indexed": indexed,
            "skipped": skipped,
            "failed": failed,
        }
    )

    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format=("%(asctime)s %(levelname)s %(name)s: %(message)s"),
    )

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
