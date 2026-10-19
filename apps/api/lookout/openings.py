from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlmodel import Session, select

from lookout.models import Opening

if TYPE_CHECKING:
    from lookout.collectors.base import RawOpening


def insert_opening(session: Session, raw: RawOpening) -> Opening:
    dedup_key = f"{raw.company.strip().casefold()}|{raw.title.strip().casefold()}"
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
    )
    session.add(opening)
    session.flush()
    return opening


def get_opening(session: Session, opening_id: uuid.UUID) -> Opening | None:
    return session.get(Opening, opening_id)


def list_openings(
    session: Session, *, limit: int = 100, offset: int = 0
) -> list[Opening]:
    statement = select(Opening).order_by(Opening.collected_at.desc(), Opening.id)
    return list(session.exec(statement.offset(offset).limit(limit)).all())


def list_dedup_keys(session: Session) -> list[str]:
    statement = select(Opening.dedup_key).order_by(Opening.dedup_key)
    return list(session.exec(statement).all())
