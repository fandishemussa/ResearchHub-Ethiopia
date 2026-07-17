"""Add versioned embeddings, trends, jobs, usage, and summary provenance.

Revision ID: 0008_ai_operations_foundation
Revises: 0007_research_intelligence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0008_ai_operations_foundation"
down_revision: str | None = "0007_research_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)
    op.create_table(
        "publication_embeddings",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("publication_id", uuid, sa.ForeignKey("publications.id"), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("model_version", sa.String(120)),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("publication_id", "model_name"),
    )
    op.create_index(
        "ix_publication_embeddings_publication_id", "publication_embeddings", ["publication_id"]
    )
    op.create_index(
        "ix_publication_embeddings_model_name", "publication_embeddings", ["model_name"]
    )
    op.create_index(
        "ix_publication_embeddings_content_hash", "publication_embeddings", ["content_hash"]
    )
    op.create_index(
        "ix_publication_embeddings_vector_hnsw",
        "publication_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.add_column(
        "publication_summaries",
        sa.Column("language", sa.String(20), nullable=False, server_default="en"),
    )
    op.add_column(
        "publication_summaries",
        sa.Column("source_type", sa.String(30), nullable=False, server_default="metadata"),
    )
    op.add_column(
        "publication_summaries",
        sa.Column("model_provider", sa.String(40), nullable=False, server_default="local"),
    )
    op.add_column("publication_summaries", sa.Column("verified_by", uuid))
    op.add_column("publication_summaries", sa.Column("verified_at", timestamp))
    op.add_column("publication_summaries", sa.Column("edited_text", sa.Text()))

    op.create_table(
        "research_trends",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("scope_type", sa.String(40), nullable=False),
        sa.Column("scope_id", uuid),
        sa.Column("trend_type", sa.String(60), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("publication_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("previous_period_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("growth_rate", sa.Numeric(10, 4)),
        sa.Column("trend_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("methodology", sa.Text(), nullable=False),
        sa.Column(
            "supporting_publication_ids", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("generated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    for column in ("scope_type", "scope_id", "trend_type", "label", "period_start", "period_end"):
        op.create_index(f"ix_research_trends_{column}", "research_trends", [column])
    op.create_index(
        "ix_research_trends_scope_period",
        "research_trends",
        ["scope_type", "scope_id", "period_start", "period_end"],
    )

    op.create_table(
        "ai_jobs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("job_type", sa.String(60), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", uuid),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(40), nullable=False, server_default="local"),
        sa.Column("model_name", sa.String(255)),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_percentage", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("input_hash", sa.String(64)),
        sa.Column("result_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_by", uuid),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", timestamp),
        sa.Column("completed_at", timestamp),
    )
    for column in ("job_type", "entity_type", "entity_id", "status", "input_hash"):
        op.create_index(f"ix_ai_jobs_{column}", "ai_jobs", [column])

    op.create_table(
        "ai_usage_logs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error_type", sa.String(120)),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    for column in ("user_id", "operation", "provider", "model_name", "success", "created_at"):
        op.create_index(f"ix_ai_usage_logs_{column}", "ai_usage_logs", [column])


def downgrade() -> None:
    op.drop_table("ai_usage_logs")
    op.drop_table("ai_jobs")
    op.drop_table("research_trends")
    for column in (
        "edited_text",
        "verified_at",
        "verified_by",
        "model_provider",
        "source_type",
        "language",
    ):
        op.drop_column("publication_summaries", column)
    op.drop_table("publication_embeddings")
