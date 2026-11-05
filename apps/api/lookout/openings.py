from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlmodel import Session, select

from lookout.models import Opening
from lookout.normalize import dedup_key as normalize_dedup_key

if TYPE_CHECKING:
    from lookout.collectors.base import RawOpening


def insert_opening(session: Session, raw: RawOpening) -> Opening:
    dedup_key = normalize_dedup_key(raw.company, raw.title)
    opening = Opening(
        source=raw.source,
        external_id=raw.external_id,
        company=raw.company,
        title=raw.title,
        location=raw.location,
        url=raw.url,
        description=raw.description,
        posted_at=raw.posted_at,
        dedup_key=dedup_key,
        raw=raw.raw,
        application_email=raw.application_email,
    )
    session.add(opening)
    session.flush()
    return opening


def get_opening(session: Session, opening_id: uuid.UUID) -> Opening | None:
    return session.get(Opening, opening_id)


def list_openings(session: Session, *, limit: int = 100, offset: int = 0) -> list[Opening]:
    statement = select(Opening).order_by(Opening.collected_at.desc(), Opening.id)
    return list(session.exec(statement.offset(offset).limit(limit)).all())


def list_dedup_keys(session: Session) -> list[str]:
    # Recompute old keys as well, so normalization fixes apply to existing data.
    statement = select(Opening.company, Opening.title)
    return [normalize_dedup_key(company, title) for company, title in session.exec(statement)]
