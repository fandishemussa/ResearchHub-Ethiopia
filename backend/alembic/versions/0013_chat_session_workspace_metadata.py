"""Add chat workspace metadata.

Revision ID: 0013_chat_workspace
Revises: 0012_document_chunks
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_chat_workspace"
down_revision: str | None = "0012_document_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("last_model_name", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_chat_sessions_pinned_updated",
        "chat_sessions",
        ["is_pinned", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_pinned_updated", table_name="chat_sessions")
    op.drop_column("chat_sessions", "last_model_name")
    op.drop_column("chat_sessions", "is_pinned")
