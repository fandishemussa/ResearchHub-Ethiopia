"""Deterministic, explainable research-intelligence services."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from hashlib import sha256
from uuid import UUID

from researchhub_ai.text_builder import PublicationTextBuilder
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from researchhub.application.full_text_summary import summarize_document_chunks
from researchhub.application.publication_documents import PublicationDocumentResolver
from researchhub.infrastructure.persistence.models import (
    DocumentChunk,
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


@dataclass(slots=True)
class SummaryOutcome:
    publication_id: UUID
    summary_type: str
    summary_text: str | None
    source_type: str
    status: str = "ready"
    id: UUID | None = None
    model_name: str | None = None
    model_version: str | None = None
    source_fields: list[str] | None = None
    confidence_score: Decimal | None = None
    is_verified: bool = False
    generated_at: datetime | None = None
    research_document_id: UUID | None = None
    document_status: str | None = None
    pages_used: list[int] | None = None
    chunk_count: int = 0
    provider: str = "local"
    cached: bool = False
    warnings: list[str] | None = None
    processing_job_id: str | None = None
    message: str | None = None


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
        self,
        publication_id: UUID,
        summary_type: str,
        max_length: int,
        force: bool = False,
        *,
        summary_scope: str = "auto",
    ) -> SummaryOutcome:
        publication = await self.publication(publication_id)
        built = PublicationTextBuilder().build_summary_text(publication)
        resolver = PublicationDocumentResolver(self.session)
        resolved = await resolver.resolve(publication_id)

        if summary_scope in {"auto", "full_text"} and resolved.indexed:
            chunks = list(
                (
                    await self.session.scalars(
                        select(DocumentChunk)
                        .where(DocumentChunk.document_id == resolved.research_document_id)
                        .order_by(
                            DocumentChunk.page_start.asc().nulls_last(),
                            DocumentChunk.page_end.asc().nulls_last(),
                            DocumentChunk.chunk_index,
                        )
                    )
                ).all()
            )
            generated = summarize_document_chunks(chunks)
            content_hash = sha256(
                f"{resolved.checksum_sha256}:{generated.content_hash}:{summary_type}:summary-v2".encode()
            ).hexdigest()
            cached = (
                None
                if force
                else await self.session.scalar(
                    select(PublicationSummary).where(
                        PublicationSummary.publication_id == publication_id,
                        PublicationSummary.summary_type == summary_type,
                        PublicationSummary.content_hash == content_hash,
                        PublicationSummary.is_stale.is_(False),
                    )
                )
            )
            if cached:
                return self._summary_outcome(cached, resolved.document_status, cached=True)
            await self.session.execute(
                update(PublicationSummary)
                .where(
                    PublicationSummary.publication_id == publication_id,
                    PublicationSummary.source_type != "full_text",
                )
                .values(is_stale=True)
            )
            result = PublicationSummary(
                publication_id=publication_id,
                summary_type=summary_type,
                summary_text=generated.text,
                model_name="page-aware-extractive-v2",
                model_version="2",
                model_provider="local",
                source_type="full_text",
                source_fields=["document_chunks"],
                content_hash=content_hash,
                confidence_score=Decimal("0.9000"),
                research_document_id=resolved.research_document_id,
                document_checksum=resolved.checksum_sha256,
                pages_used=generated.pages_used,
                chunk_count=generated.chunk_count,
                prompt_version="summary-v2",
            )
            self.session.add(result)
            await self.session.commit()
            await self.session.refresh(result)
            return self._summary_outcome(result, resolved.document_status)

        processing_job_id: str | None = None
        if summary_scope in {"auto", "full_text"}:
            processing_job_id, resolved = await resolver.prepare_for_indexing(resolved)
        if processing_job_id:
            return SummaryOutcome(
                publication_id=publication_id,
                summary_type=summary_type,
                summary_text=None,
                source_type="unavailable",
                status="processing",
                research_document_id=resolved.research_document_id,
                document_status=resolved.document_status or "pending",
                warnings=resolved.warnings,
                processing_job_id=processing_job_id,
                message=(
                    "The full document is being indexed. The summary will be available when "
                    "processing completes."
                ),
            )

        if summary_scope == "full_text":
            processing = bool(
                resolved.research_document_id
                and resolved.document_status
                not in {"failed", "restricted", "embargoed", "missing", "corrupted"}
            )
            return SummaryOutcome(
                publication_id=publication_id,
                summary_type=summary_type,
                summary_text=None,
                source_type="unavailable",
                status="processing" if processing else "unavailable",
                research_document_id=resolved.research_document_id,
                document_status=resolved.document_status or "missing",
                warnings=resolved.warnings,
                message=(
                    "The full document is being indexed. The summary will be available when "
                    "processing completes."
                    if processing
                    else "An indexed full document is not available for this publication."
                ),
            )

        use_abstract = summary_scope in {"auto", "abstract"} and bool(publication.abstract)
        source_type = "abstract" if use_abstract else "metadata"
        content_hash = sha256(
            f"{built.content_hash}:{source_type}:{summary_type}".encode()
        ).hexdigest()
        if not force:
            cached = await self.session.scalar(
                select(PublicationSummary).where(
                    PublicationSummary.publication_id == publication_id,
                    PublicationSummary.summary_type == summary_type,
                    PublicationSummary.content_hash == content_hash,
                )
            )
            if cached and not cached.is_stale:
                return self._summary_outcome(cached, resolved.document_status, cached=True)
        result = PublicationSummary(
            publication_id=publication_id,
            summary_type=summary_type,
            summary_text=summarize_text(
                publication.title,
                publication.abstract if use_abstract else None,
                summary_type,
                max_length,
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
        warnings = list(resolved.warnings)
        if source_type == "abstract" and summary_scope == "auto":
            warnings.append(
                "Full text was not available. This summary was generated from the abstract only."
            )
        return self._summary_outcome(result, resolved.document_status, warnings=warnings)

    @staticmethod
    def _summary_outcome(
        item: PublicationSummary,
        document_status: str | None,
        *,
        cached: bool = False,
        warnings: list[str] | None = None,
    ) -> SummaryOutcome:
        return SummaryOutcome(
            id=item.id,
            publication_id=item.publication_id,
            summary_type=item.summary_type,
            summary_text=item.edited_text or item.summary_text,
            source_type=item.source_type,
            model_name=item.model_name,
            model_version=item.model_version,
            source_fields=item.source_fields,
            confidence_score=item.confidence_score,
            is_verified=item.is_verified,
            generated_at=item.generated_at,
            research_document_id=item.research_document_id,
            document_status=document_status,
            pages_used=item.pages_used,
            chunk_count=item.chunk_count,
            provider=item.model_provider,
            cached=cached,
            warnings=warnings or [],
        )

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
        filters: list[ColumnElement[bool]] = [
            Publication.normalized_title.ilike(f"%{title_prefix}%")
        ]
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
