"""Add pgvector publication embeddings.

Revision ID: 0005_publication_embeddings
Revises: 0004_metadata_quality_assessment
Create Date: 2026-07-12
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0005_publication_embeddings"
down_revision = "0004_metadata_quality_assessment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Enable pgvector and add nullable embedding metadata."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("publications", sa.Column("embedding", Vector(384), nullable=True))
    op.add_column("publications", sa.Column("embedding_model", sa.String(255), nullable=True))
    op.add_column(
        "publications",
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_publications_embedding_hnsw "
        "ON publications USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Remove embedding storage while retaining the shared extension."""

    op.execute("DROP INDEX IF EXISTS ix_publications_embedding_hnsw")
    op.drop_column("publications", "embedded_at")
    op.drop_column("publications", "embedding_model")
    op.drop_column("publications", "embedding")
