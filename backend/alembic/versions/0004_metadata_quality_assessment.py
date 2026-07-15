"""Expand metadata quality assessment reports.

Revision ID: 0004_metadata_quality_assessment
Revises: 0003_metadata_pipeline
Create Date: 2026-07-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_metadata_quality_assessment"
down_revision = "0003_metadata_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add dimension scores, issue details, grades, and current-history flags."""

    op.add_column(
        "quality_reports",
        sa.Column("completeness_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "quality_reports",
        sa.Column("validity_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "quality_reports",
        sa.Column("consistency_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "quality_reports",
        sa.Column("uniqueness_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "quality_reports",
        sa.Column("timeliness_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "quality_reports",
        sa.Column("accessibility_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "quality_reports",
        sa.Column("final_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "quality_reports",
        sa.Column("grade", sa.String(1), nullable=False, server_default="F"),
    )
    op.add_column(
        "quality_reports",
        sa.Column(
            "validation_errors",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "quality_reports",
        sa.Column(
            "recommendations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "quality_reports",
        sa.Column(
            "issue_types",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "quality_reports",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "quality_reports",
        sa.Column(
            "assessed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "quality_reports",
        sa.Column(
            "ruleset_version",
            sa.String(40),
            nullable=False,
            server_default="metadata-quality-v1",
        ),
    )

    op.execute("UPDATE quality_reports SET final_score = score WHERE final_score = 0")
    op.execute(
        """
        UPDATE quality_reports
        SET grade = CASE
            WHEN final_score >= 90 THEN 'A'
            WHEN final_score >= 80 THEN 'B'
            WHEN final_score >= 70 THEN 'C'
            WHEN final_score >= 60 THEN 'D'
            ELSE 'F'
        END
        """
    )

    op.create_index("ix_quality_reports_assessed_at", "quality_reports", ["assessed_at"])
    op.create_index("ix_quality_reports_final_score", "quality_reports", ["final_score"])
    op.create_index("ix_quality_reports_grade", "quality_reports", ["grade"])
    op.create_index("ix_quality_reports_is_current", "quality_reports", ["is_current"])
    op.create_index("ix_quality_reports_ruleset_version", "quality_reports", ["ruleset_version"])
    op.create_index(
        "ix_quality_reports_publication_current",
        "quality_reports",
        ["publication_id", "is_current"],
    )
    op.create_index(
        "ix_quality_reports_grade_score",
        "quality_reports",
        ["grade", "final_score"],
    )


def downgrade() -> None:
    """Remove expanded quality assessment columns."""

    op.drop_index("ix_quality_reports_grade_score", table_name="quality_reports")
    op.drop_index("ix_quality_reports_publication_current", table_name="quality_reports")
    op.drop_index("ix_quality_reports_ruleset_version", table_name="quality_reports")
    op.drop_index("ix_quality_reports_is_current", table_name="quality_reports")
    op.drop_index("ix_quality_reports_grade", table_name="quality_reports")
    op.drop_index("ix_quality_reports_final_score", table_name="quality_reports")
    op.drop_index("ix_quality_reports_assessed_at", table_name="quality_reports")

    op.drop_column("quality_reports", "ruleset_version")
    op.drop_column("quality_reports", "assessed_at")
    op.drop_column("quality_reports", "is_current")
    op.drop_column("quality_reports", "issue_types")
    op.drop_column("quality_reports", "recommendations")
    op.drop_column("quality_reports", "validation_errors")
    op.drop_column("quality_reports", "grade")
    op.drop_column("quality_reports", "final_score")
    op.drop_column("quality_reports", "accessibility_score")
    op.drop_column("quality_reports", "timeliness_score")
    op.drop_column("quality_reports", "uniqueness_score")
    op.drop_column("quality_reports", "consistency_score")
    op.drop_column("quality_reports", "validity_score")
    op.drop_column("quality_reports", "completeness_score")
