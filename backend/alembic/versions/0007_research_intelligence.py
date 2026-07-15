"""Add summary, AI keyword, citation, and duplicate candidate records.

Revision ID: 0007_research_intelligence
Revises: 0006_research_chatbot
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_research_intelligence"
down_revision: str | None = "0006_research_chatbot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)
    op.create_table(
        "publication_summaries",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("publication_id", uuid, sa.ForeignKey("publications.id"), nullable=False),
        sa.Column("summary_type", sa.String(50), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("model_version", sa.String(120)),
        sa.Column("source_fields", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("generated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("publication_id", "summary_type", "content_hash"),
    )
    for c in ("publication_id", "summary_type", "content_hash", "is_verified"):
        op.create_index(f"ix_publication_summaries_{c}", "publication_summaries", [c])
    op.create_table(
        "publication_keywords_ai",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("publication_id", uuid, sa.ForeignKey("publications.id"), nullable=False),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("extraction_method", sa.String(80), nullable=False),
        sa.Column("model_name", sa.String(255)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("generated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("publication_id", "keyword", "extraction_method"),
    )
    for c in ("publication_id", "keyword", "extraction_method", "status"):
        op.create_index(f"ix_publication_keywords_ai_{c}", "publication_keywords_ai", [c])
    op.create_table(
        "publication_citations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("publication_id", uuid, sa.ForeignKey("publications.id"), nullable=False),
        sa.Column("citation_style", sa.String(40), nullable=False),
        sa.Column("citation_text", sa.Text(), nullable=False),
        sa.Column("metadata_version", sa.String(64), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("generated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("publication_id", "citation_style", "metadata_version"),
    )
    for c in ("publication_id", "citation_style", "metadata_version"):
        op.create_index(f"ix_publication_citations_{c}", "publication_citations", [c])
    op.create_table(
        "duplicate_candidates",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("publication_id", uuid, sa.ForeignKey("publications.id"), nullable=False),
        sa.Column(
            "candidate_publication_id", uuid, sa.ForeignKey("publications.id"), nullable=False
        ),
        sa.Column("title_similarity", sa.Numeric(5, 4), nullable=False),
        sa.Column("abstract_similarity", sa.Numeric(5, 4), nullable=False),
        sa.Column("author_similarity", sa.Numeric(5, 4), nullable=False),
        sa.Column("year_similarity", sa.Numeric(5, 4), nullable=False),
        sa.Column("doi_match", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("final_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="detected"),
        sa.Column("detected_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_by", uuid),
        sa.Column("reviewed_at", timestamp),
        sa.UniqueConstraint("publication_id", "candidate_publication_id"),
    )
    for c in ("publication_id", "candidate_publication_id", "final_score", "status"):
        op.create_index(f"ix_duplicate_candidates_{c}", "duplicate_candidates", [c])
    op.create_index(
        "ix_duplicate_candidates_status_score", "duplicate_candidates", ["status", "final_score"]
    )


def downgrade() -> None:
    for table in (
        "duplicate_candidates",
        "publication_citations",
        "publication_keywords_ai",
        "publication_summaries",
    ):
        op.drop_table(table)
