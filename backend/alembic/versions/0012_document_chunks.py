"""Add downloaded research documents and vectorized chunks.

Revision ID: 0012_document_chunks
Revises: 0011_concurrency_indexes
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0012_document_chunks"
down_revision: str | None = "0011_concurrency_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create research document and chunk storage."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)

    op.create_table(
        "research_documents",
        sa.Column(
            "id",
            uuid,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "publication_id",
            uuid,
            sa.ForeignKey(
                "publications.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
        ),
        sa.Column(
            "external_id",
            sa.String(500),
            nullable=True,
        ),
        sa.Column(
            "title",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "local_path",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "document_url",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "landing_url",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "filename",
            sa.String(1000),
            nullable=True,
        ),
        sa.Column(
            "mime_type",
            sa.String(255),
            nullable=True,
        ),
        sa.Column(
            "file_extension",
            sa.String(20),
            nullable=True,
        ),
        sa.Column(
            "checksum_sha256",
            sa.String(64),
            nullable=True,
        ),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "page_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "character_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "chunk_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "extraction_status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "extraction_error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "downloaded_at",
            timestamp,
            nullable=True,
        ),
        sa.Column(
            "extracted_at",
            timestamp,
            nullable=True,
        ),
        sa.Column(
            "indexed_at",
            timestamp,
            nullable=True,
        ),
        sa.Column(
            "created_at",
            timestamp,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            timestamp,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "local_path",
            name="uq_research_documents_local_path",
        ),
    )

    op.create_index(
        "ix_research_documents_publication_id",
        "research_documents",
        ["publication_id"],
    )
    op.create_index(
        "ix_research_documents_source",
        "research_documents",
        ["source"],
    )
    op.create_index(
        "ix_research_documents_external_id",
        "research_documents",
        ["external_id"],
    )
    op.create_index(
        "ix_research_documents_checksum_sha256",
        "research_documents",
        ["checksum_sha256"],
    )
    op.create_index(
        "ix_research_documents_extraction_status",
        "research_documents",
        ["extraction_status"],
    )
    op.create_index(
        "ix_research_documents_source_status",
        "research_documents",
        ["source", "extraction_status"],
    )

    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            uuid,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            uuid,
            sa.ForeignKey(
                "research_documents.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "page_start",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "page_end",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "section_title",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "character_count",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "embedding",
            Vector(384),
            nullable=True,
        ),
        sa.Column(
            "embedding_model",
            sa.String(255),
            nullable=True,
        ),
        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=True,
        ),
        sa.Column(
            "chunk_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "embedded_at",
            timestamp,
            nullable=True,
        ),
        sa.Column(
            "created_at",
            timestamp,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
    )

    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
    )
    op.create_index(
        "ix_document_chunks_content_hash",
        "document_chunks",
        ["content_hash"],
    )
    op.create_index(
        "ix_document_chunks_document_page",
        "document_chunks",
        ["document_id", "page_start", "page_end"],
    )

    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={
            "embedding": "vector_cosine_ops",
        },
    )


def downgrade() -> None:
    """Remove research document and chunk storage."""

    op.drop_index(
        "ix_document_chunks_embedding_hnsw",
        table_name="document_chunks",
    )
    op.drop_index(
        "ix_document_chunks_document_page",
        table_name="document_chunks",
    )
    op.drop_index(
        "ix_document_chunks_content_hash",
        table_name="document_chunks",
    )
    op.drop_index(
        "ix_document_chunks_document_id",
        table_name="document_chunks",
    )
    op.drop_table("document_chunks")

    op.drop_index(
        "ix_research_documents_source_status",
        table_name="research_documents",
    )
    op.drop_index(
        "ix_research_documents_extraction_status",
        table_name="research_documents",
    )
    op.drop_index(
        "ix_research_documents_checksum_sha256",
        table_name="research_documents",
    )
    op.drop_index(
        "ix_research_documents_external_id",
        table_name="research_documents",
    )
    op.drop_index(
        "ix_research_documents_source",
        table_name="research_documents",
    )
    op.drop_index(
        "ix_research_documents_publication_id",
        table_name="research_documents",
    )
    op.drop_table("research_documents")
