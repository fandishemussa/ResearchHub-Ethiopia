"""Idempotently seed clearly labelled, non-official enterprise showcase data."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime

from researchhub.application.rbac import assign_role, seed_authorization_vocabulary
from researchhub.core.auth_security import hash_password
from researchhub.core.permissions import Roles
from researchhub.infrastructure.persistence.models import (
    Author,
    Connector,
    Department,
    Faculty,
    HarvestJob,
    Publication,
    PublicationAuthor,
    Repository,
    University,
    User,
)
from researchhub.infrastructure.persistence.session import SessionLocal
from sqlalchemy import select

DEMO_MARKER = {"demo": True, "dataset": "enterprise-showcase-v1", "official": False}


@dataclass
class Counts:
    created: int = 0
    reused: int = 0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-demo-seed", action="store_true")
    parser.add_argument("--admin-email")
    parser.add_argument("--admin-username", default="showcase-admin")
    parser.add_argument("--admin-full-name", default="Showcase Administrator")
    parser.add_argument("--admin-password-env", default="RESEARCHHUB_DEMO_ADMIN_PASSWORD")
    return parser.parse_args()


async def seed(args: argparse.Namespace) -> Counts:
    counts = Counts()
    async with SessionLocal() as session:
        rbac = await seed_authorization_vocabulary(session)
        counts.created += rbac.roles_created + rbac.permissions_created + rbac.grants_created

        university = await session.scalar(select(University).where(University.code == "HU-DEMO"))
        if university is None:
            university = University(
                code="HU-DEMO",
                name="Haramaya University (Demonstration)",
                country="Ethiopia",
                city="Haramaya",
                website_url="https://www.haramaya.edu.et/",
                metadata_json={**DEMO_MARKER, "notice": "Demonstration configuration; not an official institutional record."},
            )
            session.add(university)
            counts.created += 1
        else:
            counts.reused += 1
        await session.flush()

        faculty = await session.scalar(select(Faculty).where(Faculty.university_id == university.id, Faculty.code == "DEMO-COA"))
        if faculty is None:
            faculty = Faculty(university_id=university.id, code="DEMO-COA", name="College of Agriculture (Demonstration)")
            session.add(faculty)
            counts.created += 1
        else:
            counts.reused += 1
        await session.flush()

        department = await session.scalar(select(Department).where(Department.university_id == university.id, Department.code == "DEMO-PLANT"))
        if department is None:
            department = Department(university_id=university.id, faculty_id=faculty.id, code="DEMO-PLANT", name="Plant Sciences (Demonstration)")
            session.add(department)
            counts.created += 1
        else:
            counts.reused += 1
        await session.flush()

        repository = await session.scalar(select(Repository).where(Repository.university_id == university.id, Repository.name == "ResearchHub Demonstration Repository"))
        if repository is None:
            repository = Repository(
                university_id=university.id,
                name="ResearchHub Demonstration Repository",
                platform="demo",
                base_url="https://example.invalid/researchhub-demo",
                metadata_formats=["oai_dc"],
                is_active=False,
                metadata_json=DEMO_MARKER,
            )
            session.add(repository)
            counts.created += 1
        else:
            counts.reused += 1
        await session.flush()

        connector = await session.scalar(select(Connector).where(Connector.code == "haramaya-demo-source"))
        if connector is None:
            connector = Connector(
                code="haramaya-demo-source",
                name="Haramaya Showcase Source (Demonstration)",
                connector_type="demo",
                base_url="https://example.invalid/researchhub-demo",
                university_id=university.id,
                repository_id=repository.id,
                config=DEMO_MARKER,
                enabled=False,
                is_public=False,
                status="demo",
                description="Synthetic disabled source for offline showcase fallback.",
            )
            session.add(connector)
            counts.created += 1
        else:
            counts.reused += 1
        await session.flush()

        authors: list[Author] = []
        for index in range(1, 3):
            normalized = f"demonstration researcher {index}"
            author = await session.scalar(select(Author).where(Author.normalized_name == normalized))
            if author is None:
                author = Author(
                    full_name=f"Demonstration Researcher {index}",
                    normalized_name=normalized,
                    affiliation="Haramaya University (Demonstration)",
                    university_id=university.id,
                    department_id=department.id,
                    metadata_json=DEMO_MARKER,
                )
                session.add(author)
                counts.created += 1
            else:
                counts.reused += 1
            authors.append(author)
        await session.flush()

        titles = (
            "Demonstration Study of Climate-Resilient Cropping Systems",
            "Demonstration Analysis of University Research Metadata Quality",
            "Demonstration Review of Community-Based Water Management",
            "Demonstration Methods for Reproducible Agricultural Data",
        )
        publications: list[Publication] = []
        for index, title in enumerate(titles, start=1):
            external_id = f"enterprise-demo:{index}"
            publication = await session.scalar(select(Publication).where(Publication.source == "enterprise-demo", Publication.external_id == external_id))
            if publication is None:
                publication = Publication(
                    external_id=external_id,
                    title=title,
                    normalized_title=title.casefold(),
                    abstract="Synthetic demonstration record. It does not describe an official or completed Haramaya University study.",
                    publication_date=date(2021 + index, 1, 1),
                    publication_year=2021 + index,
                    subjects=["Demonstration data", "Research information management"],
                    language="en",
                    source="enterprise-demo",
                    source_type="demo",
                    repository_id=repository.id,
                    repository_identifier=external_id,
                    raw_record=DEMO_MARKER,
                    normalized_record=DEMO_MARKER,
                    metadata_json=DEMO_MARKER,
                    harvested_at=datetime.now(UTC),
                )
                session.add(publication)
                counts.created += 1
            else:
                counts.reused += 1
            publications.append(publication)
        await session.flush()

        for index, publication in enumerate(publications):
            author = authors[index % len(authors)]
            link = await session.scalar(select(PublicationAuthor).where(PublicationAuthor.publication_id == publication.id, PublicationAuthor.author_id == author.id))
            if link is None:
                session.add(PublicationAuthor(publication_id=publication.id, author_id=author.id, author_order=1, affiliation="Haramaya University (Demonstration)"))
                counts.created += 1
            else:
                counts.reused += 1

        demo_job = await session.scalar(select(HarvestJob).where(HarvestJob.connector_id == connector.id, HarvestJob.mode == "dry_run", HarvestJob.metadata_json["demo"].as_boolean().is_(True)))
        if demo_job is None:
            session.add(HarvestJob(
                connector_id=connector.id,
                status="completed",
                mode="dry_run",
                job_type="demo",
                dry_run=True,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                total_records=len(publications),
                fetched_records=len(publications),
                unchanged_records=len(publications),
                metadata_json=DEMO_MARKER,
                result_summary={**DEMO_MARKER, "message": "Offline showcase fallback job."},
            ))
            counts.created += 1
        else:
            counts.reused += 1

        if args.admin_email:
            password = os.getenv(args.admin_password_env)
            if not password:
                raise ValueError(f"{args.admin_password_env} must be set when --admin-email is used")
            user = await session.scalar(select(User).where(User.email == args.admin_email.strip().casefold()))
            if user is None:
                user = User(
                    email=args.admin_email.strip().casefold(),
                    username=args.admin_username.strip().casefold(),
                    full_name=args.admin_full_name.strip(),
                    password_hash=hash_password(password),
                    is_active=True,
                    is_verified=True,
                    university_id=university.id,
                )
                session.add(user)
                counts.created += 1
            else:
                counts.reused += 1
            await session.flush()
            if await assign_role(session, user.id, Roles.UNIVERSITY_ADMIN):
                counts.created += 1
            else:
                counts.reused += 1

        await session.commit()
    return counts


def main() -> int:
    args = arguments()
    if not args.confirm_demo_seed:
        print("Refusing to seed without --confirm-demo-seed")
        return 2
    try:
        counts = asyncio.run(seed(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "detail": str(exc)}, indent=2))
        return 1
    print(json.dumps({"status": "PASS", **asdict(counts), "demo_marker": DEMO_MARKER}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
