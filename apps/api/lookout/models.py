from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, UniqueConstraint
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
