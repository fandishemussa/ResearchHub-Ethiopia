"""Verify that the enterprise showcase seed is present and clearly marked."""

from __future__ import annotations

import asyncio
import json

from researchhub.infrastructure.persistence.models import Connector, Publication, University
from researchhub.infrastructure.persistence.session import SessionLocal
from sqlalchemy import func, select


async def verify() -> dict[str, object]:
    async with SessionLocal() as session:
        university = await session.scalar(select(University).where(University.code == "HU-DEMO"))
        connector = await session.scalar(select(Connector).where(Connector.code == "haramaya-demo-source"))
        publication_count = int(await session.scalar(select(func.count(Publication.id)).where(Publication.source == "enterprise-demo")) or 0)
        checks = {
            "demo_university": bool(university and university.metadata_json.get("demo") is True),
            "disabled_demo_source": bool(connector and connector.config.get("demo") is True and not connector.enabled),
            "synthetic_publications": publication_count >= 4,
        }
        return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "publication_count": publication_count}


def main() -> int:
    try:
        result = asyncio.run(verify())
    except (OSError, RuntimeError, ValueError) as exc:
        result = {"status": "FAIL", "detail": str(exc)}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
