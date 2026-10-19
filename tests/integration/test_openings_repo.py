from dataclasses import dataclass, field
from datetime import datetime

import pytest
from lookout.openings import (
    get_opening,
    insert_opening,
    list_dedup_keys,
    list_openings,
)
from sqlalchemy.exc import IntegrityError


@dataclass(frozen=True)
class RawOpeningFixture:
    source: str
    external_id: str | None
    company: str
    title: str
    location: str | None
    url: str
    description: str
    posted_at: datetime | None
    raw: dict = field(default_factory=dict)


def make_raw_opening(
    *,
    source: str = "remoteok",
    external_id: str | None = None,
    company: str = "Globex",
    title: str = "Backend Engineer",
    location: str | None = "Remote",
    url: str = "https://example.com/jobs/1",
    description: str = "",
    posted_at: datetime | None = None,
) -> RawOpeningFixture:
    return RawOpeningFixture(
        source=source,
        external_id=external_id,
        company=company,
        title=title,
        location=location,
        url=url,
        description=description,
        posted_at=posted_at,
    )


def test_insert_and_get_opening(session):
    opening = insert_opening(session, make_raw_opening())

    assert get_opening(session, opening.id).dedup_key == "globex|backend engineer"


def test_same_source_external_id_cannot_be_inserted_twice(session):
    raw = make_raw_opening(external_id="42")
    insert_opening(session, raw)

    with pytest.raises(IntegrityError):
        insert_opening(session, raw)


def test_list_openings_and_dedup_keys(session):
    insert_opening(session, make_raw_opening())

    assert list_openings(session)[0].company == "Globex"
    assert list_dedup_keys(session) == ["globex|backend engineer"]
