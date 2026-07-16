from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from researchhub.application.harvest_persistence import (
    HarvestPersistenceContext,
    HarvestPersistenceService,
)
from researchhub.infrastructure.persistence.session import SessionLocal
from researchhub_harvester.connectors.base import NormalizedPublication

LOGGER = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 1000
MAX_KEYWORD_LENGTH = 255
MAX_PUBLISHER_LENGTH = 255


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import normalized AAU ETD harvested JSON records "
            "into ResearchHub PostgreSQL."
        )
    )

    parser.add_argument(
        "json_file",
        type=Path,
        help="Path to the harvested AAU JSON file.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of records persisted per batch.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and map records without saving them.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    return parser.parse_args()


def parse_date(value: Any) -> date | None:
    """
    Parse common AAU publication-date formats.

    Supported examples:
    - 2023
    - 2023-06
    - 2023-06-15
    - 3/4/2022
    - January, 2025
    - ISO date/time values

    Obvious repository formatting mistakes are repaired.
    Ambiguous or corrupt dates remain None.
    """

    if not isinstance(value, str):
        return None

    original_value = value.strip()

    if not original_value:
        return None

    cleaned = original_value

    # Repair values such as:
    # 2018-06-14aau -> 2018-06-14
    cleaned = re.sub(
        r"aau$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # Repair values such as:
    # 02023-12-06 -> 2023-12-06
    cleaned = re.sub(
        r"^0(?=\d{4}-\d{2}-\d{2}$)",
        "",
        cleaned,
    )

    formats = (
        "%Y-%m-%d",
        "%Y-%m",
        "%Y",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%B, %Y",
        "%B %Y",
        "%b, %Y",
        "%b %Y",
    )

    for date_format in formats:
        try:
            parsed = datetime.strptime(
                cleaned,
                date_format,
            ).date()

            if parsed.year < 1800 or parsed.year > 2100:
                LOGGER.warning(
                    "Publication date year is outside the allowed range: %s",
                    original_value,
                )
                return None

            return parsed

        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(
            cleaned.replace("Z", "+00:00")
        ).date()

        if parsed.year < 1800 or parsed.year > 2100:
            LOGGER.warning(
                "Publication date year is outside the allowed range: %s",
                original_value,
            )
            return None

        return parsed

    except ValueError:
        LOGGER.warning(
            "Unable to parse publication date: %s",
            original_value,
        )
        return None


def parse_datetime(value: Any) -> datetime:
    """
    Parse an ISO datetime value.

    When the value is missing or invalid, return the current UTC datetime.
    """

    if not isinstance(value, str) or not value.strip():
        return datetime.now(UTC)

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        return parsed

    except ValueError:
        LOGGER.warning(
            "Unable to parse datetime value: %s",
            value,
        )
        return datetime.now(UTC)


def string_list(value: Any) -> list[str]:
    """
    Convert a JSON list into a cleaned list of strings.
    """

    if not isinstance(value, list):
        return []

    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def first_string(value: Any) -> str | None:
    """
    Return the first non-empty string from a JSON list.
    """

    values = string_list(value)
    return values[0] if values else None


def deduplicate_case_insensitive(
        values: list[str],
) -> list[str]:
    """
    Remove duplicate strings using case-insensitive comparison.

    Whitespace is normalized before comparison.
    """

    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        cleaned = " ".join(value.split()).strip()

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

    return result


def clean_keywords(
        values: list[str],
        *,
        max_length: int = MAX_KEYWORD_LENGTH,
) -> list[str]:
    """
    Clean, validate and deduplicate keyword values.

    Paragraph-sized values are skipped because they are usually abstracts
    incorrectly stored in a subject or keyword field.
    """

    cleaned_keywords: list[str] = []

    for value in values:
        cleaned = " ".join(value.split()).strip()

        if not cleaned:
            continue

        if len(cleaned) > max_length:
            LOGGER.warning(
                "Skipping oversized keyword: %s...",
                cleaned[:100],
            )
            continue

        cleaned_keywords.append(cleaned)

    return deduplicate_case_insensitive(
        cleaned_keywords
    )


def normalize_publisher(value: Any) -> str | None:
    """
    Normalize publisher names and whitespace.
    """

    if not isinstance(value, str):
        return None

    normalized = " ".join(value.split()).strip()

    if not normalized:
        return None

    aliases = {
        "A.A.U": "Addis Ababa University",
        "A.A.U.": "Addis Ababa University",
        "AAU": "Addis Ababa University",
        "Addis Ababa Univ": "Addis Ababa University",
        "Addis Ababa Univ.": "Addis Ababa University",
    }

    normalized = aliases.get(
        normalized,
        normalized,
    )

    if len(normalized) > MAX_PUBLISHER_LENGTH:
        LOGGER.warning(
            "Truncating oversized publisher value: %s...",
            normalized[:100],
        )
        normalized = normalized[:MAX_PUBLISHER_LENGTH].rstrip()

    return normalized or None


def normalize_title(value: Any) -> str | None:
    """
    Normalize and validate publication titles.
    """

    if not isinstance(value, str):
        return None

    title = " ".join(value.split()).strip()

    if not title:
        return None

    if len(title) > MAX_TITLE_LENGTH:
        LOGGER.warning(
            "Rejecting oversized title: %s...",
            title[:120],
        )
        return None

    return title


def normalize_abstract(value: Any) -> str | None:
    """
    Normalize abstract whitespace while preserving the full text.
    """

    if not isinstance(value, str):
        return None

    abstract = " ".join(value.split()).strip()

    return abstract or None


def build_external_id(
        uuid_value: Any,
        handle: Any,
) -> str | None:
    """
    Build a stable publication external identifier.
    """

    if uuid_value:
        return str(uuid_value).strip()

    if handle:
        return str(handle).strip()

    return None


def map_aau_record(
        record: dict[str, Any],
) -> NormalizedPublication:
    """
    Convert one AAU JSON record into NormalizedPublication.
    """

    uuid_value = record.get("uuid")
    handle = record.get("handle")

    external_id = build_external_id(
        uuid_value,
        handle,
    )

    title = normalize_title(
        record.get("title")
    )

    if not title:
        raise ValueError(
            "AAU record does not contain a valid title."
        )

    publication_date = parse_date(
        record.get("publication_date")
    )

    authors = deduplicate_case_insensitive(
        string_list(record.get("authors"))
    )

    subjects = clean_keywords(
        string_list(record.get("subjects"))
    )

    identifiers = deduplicate_case_insensitive(
        string_list(record.get("identifiers"))
    )

    landing_page_url = record.get(
        "landing_page_url"
    )

    if (
            isinstance(landing_page_url, str)
            and landing_page_url.strip()
    ):
        cleaned_landing_page_url = (
            landing_page_url.strip()
        )

        if (
                cleaned_landing_page_url
                not in identifiers
        ):
            identifiers.append(
                cleaned_landing_page_url
            )
    else:
        cleaned_landing_page_url = None

    document_type = (
            first_string(
                record.get("document_types")
            )
            or "Thesis"
    )

    raw_record = {
        "uuid": uuid_value,
        "handle": handle,
        "alternative_titles": record.get(
            "alternative_titles",
            [],
        ),
        "advisors": record.get(
            "advisors",
            [],
        ),
        "contributors": record.get(
            "contributors",
            [],
        ),
        "accessioned_dates": record.get(
            "accessioned_dates",
            [],
        ),
        "available_dates": record.get(
            "available_dates",
            [],
        ),
        "document_types": record.get(
            "document_types",
            [],
        ),
        "identifiers": identifiers,
        "api_url": record.get(
            "api_url"
        ),
        "last_modified": record.get(
            "last_modified"
        ),
        "in_archive": record.get(
            "in_archive"
        ),
        "discoverable": record.get(
            "discoverable"
        ),
        "withdrawn": record.get(
            "withdrawn"
        ),
        "raw_metadata": record.get(
            "raw_metadata",
            {},
        ),
        "source_urls": identifiers,
        "publication_type": document_type,
        "type": document_type,
        "original_publication_date": record.get(
            "publication_date"
        ),
        "original_subjects": record.get(
            "subjects",
            [],
        ),
    }

    repository_identifier = (
        str(handle).strip()
        if handle
        else external_id
    )

    return NormalizedPublication(
        external_id=external_id,
        title=title,
        abstract=normalize_abstract(
            record.get("abstract")
        ),
        authors=authors,
        affiliations=[
            "Addis Ababa University"
        ],
        journal=None,
        publisher=normalize_publisher(
            record.get("publisher")
        ),
        publication_date=publication_date,
        publication_year=(
            publication_date.year
            if publication_date
            else None
        ),
        keywords=subjects,
        subjects=subjects,
        language=first_string(
            record.get("languages")
        ),
        doi=None,
        orcid=None,
        issn=None,
        isbn=None,
        license=None,
        article_url=cleaned_landing_page_url,
        pdf_url=None,
        repository="AAU-ETD",
        repository_identifier=repository_identifier,
        source="aau-etd",
        source_type="dspace-discovery",
        harvested_at=parse_datetime(
            record.get("harvested_at")
        ),
        updated_at=parse_datetime(
            record.get("last_modified")
        ),
        quality_score=0.0,
        is_deleted=bool(
            record.get("withdrawn", False)
        ),
        raw_record=raw_record,
    )


def load_json_records(
        json_file: Path,
) -> list[dict[str, Any]]:
    """
    Load AAU records from a JSON array file.
    """

    if not json_file.exists():
        raise FileNotFoundError(
            f"JSON file was not found: {json_file}"
        )

    with json_file.open(
            "r",
            encoding="utf-8",
    ) as file:
        payload = json.load(file)

    if not isinstance(payload, list):
        raise ValueError(
            "The AAU JSON file must contain a JSON array."
        )

    records = [
        record
        for record in payload
        if isinstance(record, dict)
    ]

    skipped_count = (
            len(payload) - len(records)
    )

    if skipped_count:
        LOGGER.warning(
            "Skipped %s non-object JSON entries.",
            skipped_count,
        )

    return records


def write_json_file(
        path: Path,
        payload: Any,
) -> None:
    """
    Write JSON data using UTF-8.
    """

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


async def import_records(
        json_file: Path,
        batch_size: int,
        dry_run: bool,
) -> None:
    raw_records = load_json_records(
        json_file
    )

    mapped_records: list[
        NormalizedPublication
    ] = []

    mapping_errors: list[
        dict[str, Any]
    ] = []

    for index, raw_record in enumerate(
            raw_records
    ):
        try:
            mapped_record = map_aau_record(
                raw_record
            )

            mapped_records.append(
                mapped_record
            )

        except Exception as exc:
            mapping_errors.append(
                {
                    "index": index,
                    "uuid": raw_record.get(
                        "uuid"
                    ),
                    "handle": raw_record.get(
                        "handle"
                    ),
                    "title": raw_record.get(
                        "title"
                    ),
                    "error": str(exc),
                }
            )

    print(
        f"Loaded: {len(raw_records)}\n"
        f"Mapped: {len(mapped_records)}\n"
        f"Mapping errors: {len(mapping_errors)}"
    )

    error_file = json_file.with_suffix(
        ".import-errors.json"
    )

    if mapping_errors:
        write_json_file(
            error_file,
            mapping_errors,
        )

        print(
            "Mapping errors written to: "
            f"{error_file}"
        )
    elif error_file.exists():
        error_file.unlink()

    if dry_run:
        print(
            "Dry run completed. Nothing was saved."
        )
        return

    context = HarvestPersistenceContext(
        source="aau-etd",
        source_type="dspace-discovery",
        university_code="AAU",
        university_name=(
            "Addis Ababa University"
        ),
        repository_name="AAU-ETD",
        repository_base_url=(
            "https://etd.aau.edu.et"
        ),
        connector_code=(
            "aau-dspace-discovery"
        ),
    )

    totals = {
        "created_count": 0,
        "updated_count": 0,
        "unchanged_count": 0,
        "deleted_count": 0,
        "failed_count": 0,
        "duplicate_count": 0,
    }

    all_errors: list[
        dict[str, Any]
    ] = []

    async with SessionLocal() as session:
        service = HarvestPersistenceService(
            session
        )

        for start in range(
                0,
                len(mapped_records),
                batch_size,
        ):
            batch = mapped_records[
                start:start + batch_size
            ]

            try:
                result = await service.persist_many(
                    batch,
                    context,
                )

                result_data = result.asdict()

                for key in totals:
                    totals[key] += int(
                        result_data.get(
                            key,
                            0,
                        )
                    )

                all_errors.extend(
                    result_data.get(
                        "errors",
                        [],
                    )
                )

            except Exception as exc:
                LOGGER.exception(
                    "Batch persistence failed at "
                    "records %s-%s.",
                    start,
                    start + len(batch) - 1,
                    )

                totals["failed_count"] += len(
                    batch
                )

                all_errors.append(
                    {
                        "batch_start": start,
                        "batch_end": (
                                start
                                + len(batch)
                                - 1
                        ),
                        "error": str(exc),
                    }
                )

                try:
                    await session.rollback()
                except Exception:
                    LOGGER.exception(
                        "Session rollback failed."
                    )

            processed = min(
                start + len(batch),
                len(mapped_records),
                )

            print(
                f"Processed {processed}/"
                f"{len(mapped_records)}"
            )

    summary = {
        **totals,
        "loaded_count": len(raw_records),
        "mapped_count": len(mapped_records),
        "mapping_error_count": len(
            mapping_errors
        ),
        "persistence_errors": all_errors,
    }

    summary_file = json_file.with_suffix(
        ".import-summary.json"
    )

    write_json_file(
        summary_file,
        summary,
    )

    print("\nImport complete:")
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    print(
        f"Summary written to: {summary_file}"
    )


async def async_main() -> None:
    args = parse_arguments()

    if args.batch_size < 1:
        raise ValueError(
            "--batch-size must be greater "
            "than zero."
        )

    logging.basicConfig(
        level=(
            logging.DEBUG
            if args.verbose
            else logging.INFO
        ),
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        ),
    )

    await import_records(
        json_file=args.json_file,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )


def main() -> None:
    try:
        asyncio.run(
            async_main()
        )

    except KeyboardInterrupt:
        print("\nImport cancelled.")

    except Exception:
        LOGGER.exception(
            "AAU JSON import failed."
        )
        raise


if __name__ == "__main__":
    main()