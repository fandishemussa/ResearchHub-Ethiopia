"""Idempotently import Ethiopian universities from a JSON list."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from researchhub.infrastructure.persistence.models import University
from researchhub.infrastructure.persistence.session import SessionLocal
from sqlalchemy import select


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", type=Path)
    return parser.parse_args()


def unique_code(abbreviation: str, name: str, used: dict[str, str]) -> str:
    base = re.sub(r"[^A-Z0-9]", "", abbreviation.upper())[:40] or "UNIV"
    if base not in used or used[base].casefold() == name.casefold():
        return base
    words = [re.sub(r"[^A-Z0-9]", "", word.upper()) for word in name.split()]
    qualifiers = [word for word in words if word and word not in {"UNIVERSITY", "OF", "THE"}]
    for qualifier in reversed(qualifiers):
        candidate = f"{base}-{qualifier}"[:40]
        if candidate not in used or used[candidate].casefold() == name.casefold():
            return candidate
    index = 2
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"


async def import_universities(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("Expected a JSON list")
    created = 0
    updated = 0
    unchanged = 0
    async with SessionLocal() as session:
        existing = list((await session.scalars(select(University))).all())
        by_name = {item.name.casefold(): item for item in existing}
        used_codes = {item.code.upper(): item.name for item in existing}
        for index, row in enumerate(payload, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"Entry {index} is not an object")
            name = str(row.get("name") or "").strip()
            abbreviation = str(row.get("abbreviation") or "").strip()
            ownership = str(row.get("ownership") or "").strip().upper()
            if len(name) < 2 or not abbreviation or ownership not in {"PUBLIC", "PRIVATE"}:
                raise ValueError(f"Entry {index} has invalid name, abbreviation, or ownership")
            metadata = {
                "ownership": ownership,
                "original_abbreviation": abbreviation,
                "import_source": "ethiopian-universities-list",
            }
            item = by_name.get(name.casefold())
            if item is not None:
                merged = {**(item.metadata_json or {}), **metadata}
                changed = item.metadata_json != merged or not item.is_active
                item.metadata_json = merged
                item.is_active = True
                if changed:
                    updated += 1
                else:
                    unchanged += 1
                continue
            code = unique_code(abbreviation, name, used_codes)
            item = University(
                code=code,
                name=name,
                country="Ethiopia",
                is_active=True,
                metadata_json=metadata,
            )
            session.add(item)
            by_name[name.casefold()] = item
            used_codes[code] = name
            created += 1
        await session.commit()
    return {"total": len(payload), "created": created, "updated": updated, "unchanged": unchanged}


def main() -> None:
    print(json.dumps(asyncio.run(import_universities(parse_args().json_file)), indent=2))


if __name__ == "__main__":
    main()
