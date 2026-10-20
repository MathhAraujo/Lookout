from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from lookout.db import utcnow


class Opening(SQLModel, table=True):
    __tablename__ = "openings"

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_openings_source_external_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source: str
    external_id: str | None = Field(default=None)
    company: str
    title: str
    location: str | None = Field(default=None)
    url: str
    description: str = ""
    posted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    collected_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    dedup_key: str = Field(index=True)
    raw: dict = Field(default_factory=dict, sa_type=JSONB)
    application_email: str | None = Field(default=None)


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    type: str
    payload: dict = Field(default_factory=dict, sa_type=JSONB)
    status: str = Field(default="pending", index=True)
    run_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": utcnow},
    )


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    __table_args__ = (
        UniqueConstraint("opening_id", name="uq_applications_opening_id"),
        CheckConstraint(
            "lane IN ('auto_apply', 'review', 'manual_assist', 'rejected')",
            name="ck_applications_lane",
        ),
        CheckConstraint(
            "status IN ('awaiting_review', 'ready', 'manual_assist', 'rejected', "
            "'blocked', 'dry_run', 'submitting', 'submitted', 'expired')",
            name="ck_applications_status",
        ),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_applications_score"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    opening_id: UUID = Field(foreign_key="openings.id", index=True)
    lane: str
    score: int | None = Field(default=None)
    reasons: list[str] = Field(default_factory=list, sa_type=JSONB)
    red_flags: list[str] = Field(default_factory=list, sa_type=JSONB)
    status: str
    review_expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    submitted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    last_error: str | None = Field(default=None)
    dry_run: bool = True
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": utcnow},
    )


class ApplicationAnswer(SQLModel, table=True):
    __tablename__ = "application_answers"

    __table_args__ = (
        CheckConstraint(
            "source IN ('fact', 'llm', 'unresolved')",
            name="ck_application_answers_source",
        ),
        CheckConstraint(
            "status IN ('answered', 'blocked', 'skipped')",
            name="ck_application_answers_status",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    application_id: UUID = Field(foreign_key="applications.id", index=True)
    question_key: str
    source: str
    status: str
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class ApplicationArtifact(SQLModel, table=True):
    __tablename__ = "application_artifacts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    application_id: UUID = Field(foreign_key="applications.id", index=True)
    kind: str
    object_key: str
    content_type: str
    sha256: str
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class ApplicationEvent(SQLModel, table=True):
    __tablename__ = "application_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    application_id: UUID = Field(foreign_key="applications.id", index=True)
    event_type: str
    details: dict = Field(default_factory=dict, sa_type=JSONB)
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class ConnectorHealth(SQLModel, table=True):
    __tablename__ = "connector_health"

    __table_args__ = (
        UniqueConstraint("connector", name="uq_connector_health_connector"),
        CheckConstraint(
            "status IN ('healthy', 'degraded', 'unavailable')",
            name="ck_connector_health_status",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    connector: str
    status: str
    checked_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    last_success_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    detail: str | None = Field(default=None)
