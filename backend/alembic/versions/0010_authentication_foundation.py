"""Add users, RBAC vocabulary, and revocable token sessions.

Revision ID: 0010_authentication_foundation
Revises: 0009_source_management
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_authentication_foundation"
down_revision: str | None = "0009_source_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    timestamp = sa.DateTime(timezone=True)
    op.create_table(
        "users",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("university_id", uuid, sa.ForeignKey("universities.id")),
        sa.Column("faculty_id", uuid, sa.ForeignKey("faculties.id")),
        sa.Column("department_id", uuid, sa.ForeignKey("departments.id")),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", timestamp),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", timestamp),
    )
    for c in (
        "email",
        "username",
        "is_active",
        "is_verified",
        "is_suspended",
        "university_id",
        "faculty_id",
        "department_id",
        "locked_until",
    ):
        op.create_index(f"ix_users_{c}", "users", [c])
    op.create_table(
        "roles",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_roles_name", "roles", ["name"])
    op.create_table(
        "permissions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("code", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])
    op.create_table(
        "user_roles",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", uuid, sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "role_id"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_table(
        "role_permissions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("role_id", uuid, sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "permission_id",
            uuid,
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("role_id", "permission_id"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])
    op.create_table(
        "refresh_sessions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", timestamp, nullable=False),
        sa.Column("revoked_at", timestamp),
        sa.Column("replaced_by_session_id", uuid, sa.ForeignKey("refresh_sessions.id")),
        sa.Column("last_used_at", timestamp),
    )
    for c in ("user_id", "token_hash", "expires_at", "revoked_at"):
        op.create_index(f"ix_refresh_sessions_{c}", "refresh_sessions", [c])
    for table in ("password_reset_tokens", "email_verification_tokens"):
        op.create_table(
            table,
            sa.Column("id", uuid, primary_key=True),
            sa.Column(
                "user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", timestamp, nullable=False),
            sa.Column("used_at", timestamp),
            sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        )
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
        op.create_index(f"ix_{table}_token_hash", table, ["token_hash"])
        op.create_index(f"ix_{table}_expires_at", table, ["expires_at"])


def downgrade() -> None:
    for table in (
        "email_verification_tokens",
        "password_reset_tokens",
        "refresh_sessions",
        "role_permissions",
        "user_roles",
        "permissions",
        "roles",
        "users",
    ):
        op.drop_table(table)
