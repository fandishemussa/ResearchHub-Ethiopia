"""Deterministic, explainable research-intelligence services."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from hashlib import sha256
from uuid import UUID

from researchhub_ai.text_builder import PublicationTextBuilder
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from researchhub.infrastructure.persistence.models import (
    DuplicateCandidate,
    Publication,
    PublicationAuthor,
    PublicationCitationAI,
    PublicationKeyword,
    PublicationKeywordAI,
    PublicationSummary,
)

SUMMARY_TYPES = {
    "short",
    "detailed",
    "structured",
    "executive",
    "plain-language",
    "methods",
    "findings",
    "limitations",
    "policy",
}
CITATION_STYLES = {
    "apa7",
    "mla9",
    "chicago-author-date",
    "chicago-notes",
    "harvard",
    "ieee",
    "vancouver",
    "bibtex",
    "ris",
    "csl-json",
}
STOPWORDS = {
    "about",
    "after",
    "also",
    "among",
    "based",
    "been",
    "between",
    "from",
    "have",
    "into",
    "more",
    "other",
    "research",
    "results",
    "study",
    "than",
    "that",
    "their",
    "these",
    "this",
    "through",
    "using",
    "were",
    "which",
    "with",
}


def publication_content_hash(publication: Publication) -> str:
    return PublicationTextBuilder().build_summary_text(publication).content_hash


def summarize_text(
    title: str, abstract: str | None, summary_type: str, max_length: int = 900
) -> str:
    if summary_type not in SUMMARY_TYPES:
        raise ValueError("Unsupported summary type")
    if not abstract:
        return f"Abstract-only summary unavailable: {title} has no abstract in ResearchHub."
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", abstract) if part.strip()]
    count = 2 if summary_type in {"short", "plain-language"} else 5
    body = " ".join(sentences[:count])[:max_length].strip()
    prefix = "Abstract-based summary: "
    if summary_type == "structured":
        return f"Background/objective: {sentences[0]}\nEvidence reported in abstract: {' '.join(sentences[1:count]) or 'Not stated.'}\nLimitations: Not stated in the available abstract."
    return prefix + body


def extract_keywords(
    title: str, abstract: str | None, subjects: list[str], limit: int = 10
) -> list[tuple[str, float]]:
    text = f"{title} {title} {abstract or ''} {' '.join(subjects)}".casefold()
    words = re.findall(r"[a-z][a-z-]{2,}", text)
    counts = Counter(word for word in words if word not in STOPWORDS)
    if not counts:
        return []
    maximum = max(counts.values())
    return [(term, round(count / maximum, 4)) for term, count in counts.most_common(limit)]


def citation_metadata_hash(publication: Publication) -> str:
    authors = [link.author.full_name for link in publication.authors if link.author]
    data = [
        publication.title,
        publication.publication_year,
        publication.doi,
        publication.article_url,
        authors,
    ]
    return sha256(json.dumps(data, default=str).encode()).hexdigest()


def format_citation(publication: Publication, style: str) -> str:
    style = style.casefold()
    if style not in CITATION_STYLES:
        raise ValueError("Unsupported citation style")
    authors = [link.author.full_name for link in publication.authors if link.author]
    names = ", ".join(authors) if authors else "Unknown author"
    year = str(publication.publication_year or "n.d.")
    title = publication.title.rstrip(".")
    locator = (
        f"https://doi.org/{publication.doi}" if publication.doi else publication.article_url or ""
    )
    if style == "bibtex":
        key = re.sub(r"\W+", "", (authors[0].split()[-1] if authors else "ResearchHub") + year)
        return f"@misc{{{key},\n  author = {{{' and '.join(authors)}}},\n  title = {{{title}}},\n  year = {{{year}}},\n  url = {{{locator}}}\n}}"
    if style == "ris":
        author_lines = "\n".join(f"AU  - {author}" for author in authors)
        return f"TY  - GEN\n{author_lines}\nTI  - {title}\nPY  - {year}\nUR  - {locator}\nER  -"
    if style == "csl-json":
        return json.dumps(
            {
                "type": "article",
                "title": title,
                "author": [{"literal": author} for author in authors],
                "issued": {"raw": year},
                "DOI": publication.doi,
                "URL": publication.article_url,
            },
            ensure_ascii=False,
        )
    if style in {"ieee", "vancouver"}:
        return f"{names}, “{title},” {year}. {locator}".strip()
    if style in {"mla9", "chicago-notes"}:
        return f"{names}. “{title}.” {year}. {locator}".strip()
    return f"{names} ({year}). {title}. {locator}".strip()


def duplicate_score(first: Publication, second: Publication) -> dict[str, float | bool]:
    doi_match = bool(first.doi and second.doi and first.doi.casefold() == second.doi.casefold())
    title = SequenceMatcher(
        None,
        (first.normalized_title or first.title).casefold(),
        (second.normalized_title or second.title).casefold(),
    ).ratio()
    abstract = (
        SequenceMatcher(
            None, (first.abstract or "").casefold(), (second.abstract or "").casefold()
        ).ratio()
        if first.abstract and second.abstract
        else 0.0
    )
    first_authors = {
        link.author.normalized_name or link.author.full_name.casefold()
        for link in first.authors
        if link.author
    }
    second_authors = {
        link.author.normalized_name or link.author.full_name.casefold()
        for link in second.authors
        if link.author
    }
    author = (
        len(first_authors & second_authors) / min(len(first_authors), len(second_authors))
        if first_authors and second_authors
        else 0.0
    )
    year = (
        1.0
        if first.publication_year and first.publication_year == second.publication_year
        else 0.5
        if first.publication_year
        and second.publication_year
        and abs(first.publication_year - second.publication_year) == 1
        else 0.0
    )
    final = 1.0 if doi_match else title * 0.4 + abstract * 0.3 + author * 0.2 + year * 0.1
    return {
        "title_similarity": title,
        "abstract_similarity": abstract,
        "author_similarity": author,
        "year_similarity": year,
        "doi_match": doi_match,
        "final_score": final,
    }


class ResearchIntelligenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publication(self, publication_id: UUID) -> Publication:
        item = await self.session.scalar(
            select(Publication)
            .options(
                selectinload(Publication.authors).selectinload(PublicationAuthor.author),
                selectinload(Publication.keywords).selectinload(PublicationKeyword.keyword),
                selectinload(Publication.journal),
            )
            .where(Publication.id == publication_id, Publication.is_deleted.is_(False))
        )
        if item is None:
            raise LookupError("Publication not found")
        return item

    async def summarize(
        self, publication_id: UUID, summary_type: str, max_length: int, force: bool = False
    ) -> PublicationSummary:
        publication = await self.publication(publication_id)
        built = PublicationTextBuilder().build_summary_text(publication)
        content_hash = built.content_hash
        if not force:
            cached = await self.session.scalar(
                select(PublicationSummary).where(
                    PublicationSummary.publication_id == publication_id,
                    PublicationSummary.summary_type == summary_type,
                    PublicationSummary.content_hash == content_hash,
                )
            )
            if cached:
                return cached
        source_type = "abstract" if publication.abstract else "metadata"
        result = PublicationSummary(
            publication_id=publication_id,
            summary_type=summary_type,
            summary_text=summarize_text(
                publication.title, publication.abstract, summary_type, max_length
            ),
            model_name="grounded-extractive-v1",
            model_version="1",
            model_provider="local",
            source_type=source_type,
            source_fields=list(built.source_fields),
            content_hash=content_hash,
            confidence_score=Decimal("0.8000") if publication.abstract else Decimal("0.0000"),
        )
        self.session.add(result)
        await self.session.commit()
        await self.session.refresh(result)
        return result

    async def summaries(self, publication_id: UUID) -> list[PublicationSummary]:
        await self.publication(publication_id)
        return list(
            (
                await self.session.scalars(
                    select(PublicationSummary)
                    .where(PublicationSummary.publication_id == publication_id)
                    .order_by(PublicationSummary.generated_at.desc())
                )
            ).all()
        )

    async def keywords(self, publication_id: UUID, limit: int = 10) -> list[PublicationKeywordAI]:
        publication = await self.publication(publication_id)
        generated = extract_keywords(
            publication.title, publication.abstract, publication.subjects, limit
        )
        existing = {
            (item.keyword, item.extraction_method): item
            for item in (
                await self.session.scalars(
                    select(PublicationKeywordAI).where(
                        PublicationKeywordAI.publication_id == publication_id
                    )
                )
            ).all()
        }
        output = []
        for keyword, confidence in generated:
            item = existing.get((keyword, "frequency-v1")) or PublicationKeywordAI(
                publication_id=publication_id,
                keyword=keyword,
                confidence_score=Decimal(str(confidence)),
                extraction_method="frequency-v1",
                model_name="local",
            )
            if item.id is None:
                self.session.add(item)
            output.append(item)
        await self.session.commit()
        for item in output:
            if item.id is not None:
                await self.session.refresh(item)
        return output

    async def citation(self, publication_id: UUID, style: str) -> PublicationCitationAI:
        publication = await self.publication(publication_id)
        version = citation_metadata_hash(publication)
        cached = await self.session.scalar(
            select(PublicationCitationAI).where(
                PublicationCitationAI.publication_id == publication_id,
                PublicationCitationAI.citation_style == style,
                PublicationCitationAI.metadata_version == version,
            )
        )
        if cached:
            return cached
        item = PublicationCitationAI(
            publication_id=publication_id,
            citation_style=style,
            citation_text=format_citation(publication, style),
            metadata_version=version,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def trend_overview(
        self, year_from: int | None, year_to: int | None
    ) -> list[dict[str, object]]:
        statement = select(Publication.publication_year, func.count(Publication.id)).where(
            Publication.is_deleted.is_(False), Publication.publication_year.is_not(None)
        )
        if year_from:
            statement = statement.where(Publication.publication_year >= year_from)
        if year_to:
            statement = statement.where(Publication.publication_year <= year_to)
        rows = (
            await self.session.execute(
                statement.group_by(Publication.publication_year).order_by(
                    Publication.publication_year
                )
            )
        ).all()
        return [
            {
                "year": year,
                "publication_count": count,
                "methodology": "Annual frequency of active publication records; this is not an impact measure.",
            }
            for year, count in rows
        ]

    async def scan_duplicates(
        self, publication_id: UUID, threshold: float = 0.65
    ) -> list[DuplicateCandidate]:
        target = await self.publication(publication_id)
        title_prefix = " ".join((target.normalized_title or target.title).split()[:4])
        filters = [Publication.normalized_title.ilike(f"%{title_prefix}%")]
        if target.doi:
            filters.append(func.lower(Publication.doi) == target.doi.casefold())
        statement = (
            select(Publication)
            .options(selectinload(Publication.authors).selectinload(PublicationAuthor.author))
            .where(
                Publication.id != publication_id, Publication.is_deleted.is_(False), or_(*filters)
            )
            .limit(200)
        )
        candidates = list((await self.session.scalars(statement)).unique().all())
        output: list[DuplicateCandidate] = []
        for candidate in candidates:
            scores = duplicate_score(target, candidate)
            if float(scores["final_score"]) < threshold:
                continue
            first_id, second_id = sorted((target.id, candidate.id), key=str)
            existing = await self.session.scalar(
                select(DuplicateCandidate).where(
                    DuplicateCandidate.publication_id == first_id,
                    DuplicateCandidate.candidate_publication_id == second_id,
                )
            )
            if existing:
                output.append(existing)
                continue
            item = DuplicateCandidate(
                publication_id=first_id,
                candidate_publication_id=second_id,
                title_similarity=Decimal(str(round(float(scores["title_similarity"]), 4))),
                abstract_similarity=Decimal(str(round(float(scores["abstract_similarity"]), 4))),
                author_similarity=Decimal(str(round(float(scores["author_similarity"]), 4))),
                year_similarity=Decimal(str(round(float(scores["year_similarity"]), 4))),
                doi_match=bool(scores["doi_match"]),
                final_score=Decimal(str(round(float(scores["final_score"]), 4))),
            )
            self.session.add(item)
            output.append(item)
        await self.session.commit()
        for item in output:
            await self.session.refresh(item)
        return output

    async def duplicate_candidates(self, status: str | None = None) -> list[DuplicateCandidate]:
        statement = select(DuplicateCandidate)
        if status:
            statement = statement.where(DuplicateCandidate.status == status)
        return list(
            (
                await self.session.scalars(
                    statement.order_by(DuplicateCandidate.final_score.desc()).limit(200)
                )
            ).all()
        )

    async def review_duplicate(self, candidate_id: UUID, status: str) -> DuplicateCandidate:
        item = await self.session.get(DuplicateCandidate, candidate_id)
        if item is None:
            raise LookupError("Duplicate candidate not found")
        item.status = status
        item.reviewed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(item)
        return item
