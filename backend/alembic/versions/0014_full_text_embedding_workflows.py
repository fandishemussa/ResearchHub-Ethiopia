"""Add full-text summary and embedding workflow provenance.

Revision ID: 0014_full_text_embedding
Revises: 0013_chat_workspace
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_full_text_embedding"
down_revision: str | None = "0013_chat_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("embedding_content_hash", sa.String(64)))
    op.add_column("publications", sa.Column("embedding_failure_code", sa.String(80)))
    op.add_column("publications", sa.Column("embedding_failure_message", sa.Text()))
    op.add_column(
        "publications",
        sa.Column("embedding_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_publications_embedding_content_hash", "publications", ["embedding_content_hash"]
    )
    op.create_index(
        "ix_publications_embedding_failure_code", "publications", ["embedding_failure_code"]
    )
    op.add_column(
        "publication_summaries",
        sa.Column("research_document_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("publication_summaries", sa.Column("document_checksum", sa.String(64)))
    op.add_column(
        "publication_summaries",
        sa.Column("pages_used", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "publication_summaries",
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "publication_summaries",
        sa.Column("prompt_version", sa.String(80), nullable=False, server_default="summary-v2"),
    )
    op.add_column(
        "publication_summaries",
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_publication_summaries_research_document_id",
        "publication_summaries",
        "research_documents",
        ["research_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_publication_summaries_research_document_id",
        "publication_summaries",
        ["research_document_id"],
    )
    op.create_index(
        "ix_publication_summaries_document_checksum",
        "publication_summaries",
        ["document_checksum"],
    )
    op.create_index("ix_publication_summaries_is_stale", "publication_summaries", ["is_stale"])
    op.add_column("research_documents", sa.Column("processing_error_code", sa.String(80)))
    op.add_column("research_documents", sa.Column("technical_error", sa.Text()))
    op.add_column(
        "research_documents",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("research_documents", sa.Column("last_attempted_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_research_documents_processing_error_code",
        "research_documents",
        ["processing_error_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_documents_processing_error_code", table_name="research_documents")
    for column in ("last_attempted_at", "retry_count", "technical_error", "processing_error_code"):
        op.drop_column("research_documents", column)
    op.drop_index("ix_publication_summaries_is_stale", table_name="publication_summaries")
    op.drop_index("ix_publication_summaries_document_checksum", table_name="publication_summaries")
    op.drop_index(
        "ix_publication_summaries_research_document_id", table_name="publication_summaries"
    )
    op.drop_constraint(
        "fk_publication_summaries_research_document_id",
        "publication_summaries",
        type_="foreignkey",
    )
    for column in (
        "is_stale",
        "prompt_version",
        "chunk_count",
        "pages_used",
        "document_checksum",
        "research_document_id",
    ):
        op.drop_column("publication_summaries", column)
    op.drop_index("ix_publications_embedding_failure_code", table_name="publications")
    op.drop_index("ix_publications_embedding_content_hash", table_name="publications")
    for column in (
        "embedding_retry_count",
        "embedding_failure_message",
        "embedding_failure_code",
        "embedding_content_hash",
    ):
        op.drop_column("publications", column)
