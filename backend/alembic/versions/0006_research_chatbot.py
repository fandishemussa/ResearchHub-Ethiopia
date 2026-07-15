"""Add grounded research chatbot persistence.

Revision ID: 0006_research_chatbot
Revises: 0005_publication_embeddings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_research_chatbot"
down_revision: str | None = "0005_publication_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("universities.id")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("user_id", "university_id", "is_deleted"):
        op.create_index(f"ix_chat_sessions_{column}", "chat_sessions", [column])
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("retrieved_publication_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("model_name", sa.String(255)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("usage", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("session_id", "role", "created_at"):
        op.create_index(f"ix_chat_messages_{column}", "chat_messages", [column])
    op.create_table(
        "chat_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("rating", sa.String(40), nullable=False),
        sa.Column("comment", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("message_id", "user_id"),
    )
    op.create_index("ix_chat_feedback_message_id", "chat_feedback", ["message_id"])
    op.create_index("ix_chat_feedback_user_id", "chat_feedback", ["user_id"])
    op.create_index("ix_chat_feedback_rating", "chat_feedback", ["rating"])


def downgrade() -> None:
    op.drop_table("chat_feedback")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
