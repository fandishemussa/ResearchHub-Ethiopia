"""Bounded administrator operations for publication embeddings."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.api.v1.dependencies import get_db_session, require_permission
from researchhub.application.worker import celery_app
from researchhub.core.config import get_settings
from researchhub.core.permissions import Permissions
from researchhub.infrastructure.persistence.models import Publication

router = APIRouter(
    prefix="/admin/ai/embeddings",
    tags=["admin-ai"],
    dependencies=[Depends(require_permission(Permissions.AI_MANAGE))],
)


@router.get("")
async def embedding_status(session: AsyncSession = Depends(get_db_session)) -> dict[str, object]:
    settings = get_settings()
    total = int(await session.scalar(select(func.count(Publication.id))) or 0)
    embedded = int(
        await session.scalar(
            select(func.count(Publication.id)).where(Publication.embedding.is_not(None))
        )
        or 0
    )
    stale = int(
        await session.scalar(
            select(func.count(Publication.id)).where(
                Publication.embedding.is_not(None),
                or_(
                    Publication.embedding_content_hash.is_(None),
                    Publication.embedding_model != settings.embedding_model,
                ),
            )
        )
        or 0
    )
    failed = int(
        await session.scalar(
            select(func.count(Publication.id)).where(
                Publication.embedding_failure_code.is_not(None)
            )
        )
        or 0
    )
    return {
        "total_publications": total,
        "embedded_publications": embedded,
        "missing_embeddings": total - embedded,
        "stale_embeddings": stale,
        "failed_embeddings": failed,
        "embedding_model": settings.embedding_model,
        "vector_dimension": 384,
        "queue": "ai_embeddings",
    }


@router.post("/generate")
async def generate_embeddings(
    mode: str = Query(default="missing", pattern="^(missing|stale|failed)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    source: str | None = Query(default=None, max_length=120),
    university_id: UUID | None = None,
) -> dict[str, str]:
    task = celery_app.send_task(
        "researchhub.embeddings.generate",
        kwargs={
            "source": source,
            "limit": limit,
            "force": mode == "stale",
            "failed_only": mode == "failed",
            "university_id": str(university_id) if university_id else None,
        },
    )
    return {"status": "queued", "task_id": task.id}


@router.post("/publications/{publication_id}")
async def generate_one(publication_id: UUID) -> dict[str, str]:
    task = celery_app.send_task(
        "researchhub.embeddings.generate_publication", args=[str(publication_id)]
    )
    return {"status": "queued", "task_id": task.id}
