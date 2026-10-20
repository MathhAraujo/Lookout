"""add phase 2 application workflow tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("openings", sa.Column("application_email", sa.String(), nullable=True))

    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opening_id", sa.Uuid(), nullable=False),
        sa.Column("lane", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("red_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("review_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lane IN ('auto_apply', 'review', 'manual_assist', 'rejected')",
            name="ck_applications_lane",
        ),
        sa.CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_applications_score"),
        sa.CheckConstraint(
            "status IN ('awaiting_review', 'ready', 'manual_assist', 'rejected', "
            "'blocked', 'dry_run', 'submitting', 'submitted', 'expired')",
            name="ck_applications_status",
        ),
        sa.ForeignKeyConstraint(["opening_id"], ["openings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opening_id", name="uq_applications_opening_id"),
    )
    op.create_index(
        op.f("ix_applications_opening_id"), "applications", ["opening_id"], unique=False
    )

    op.create_table(
        "application_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("question_key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('fact', 'llm', 'unresolved')",
            name="ck_application_answers_source",
        ),
        sa.CheckConstraint(
            "status IN ('answered', 'blocked', 'skipped')",
            name="ck_application_answers_status",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_application_answers_application_id"),
        "application_answers",
        ["application_id"],
        unique=False,
    )

    op.create_table(
        "application_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_application_artifacts_application_id"),
        "application_artifacts",
        ["application_id"],
        unique=False,
    )

    op.create_table(
        "application_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_application_events_application_id"),
        "application_events",
        ["application_id"],
        unique=False,
    )

    op.create_table(
        "connector_health",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connector", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.CheckConstraint(
            "status IN ('healthy', 'degraded', 'unavailable')",
            name="ck_connector_health_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector", name="uq_connector_health_connector"),
    )


def downgrade() -> None:
    op.drop_table("connector_health")
    op.drop_index(op.f("ix_application_events_application_id"), table_name="application_events")
    op.drop_table("application_events")
    op.drop_index(
        op.f("ix_application_artifacts_application_id"), table_name="application_artifacts"
    )
    op.drop_table("application_artifacts")
    op.drop_index(
        op.f("ix_application_answers_application_id"), table_name="application_answers"
    )
    op.drop_table("application_answers")
    op.drop_index(op.f("ix_applications_opening_id"), table_name="applications")
    op.drop_table("applications")
    op.drop_column("openings", "application_email")
