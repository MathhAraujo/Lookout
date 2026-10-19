from datetime import datetime

from lookout.collectors.base import CollectorError, RawOpening
from lookout.config import get_settings
from lookout.ingest import IngestStats, collect_all, ingest


def make_raw(
    company: str,
    title: str,
    *,
    source: str = "remoteok",
    external_id: str | None = None,
    location: str | None = "Remote",
    url: str = "https://example.com/jobs/1",
    description: str = "",
    posted_at: datetime | None = None,
    raw: dict | None = None,
) -> RawOpening:
    return RawOpening(
        source=source,
        external_id=external_id,
        company=company,
        title=title,
        location=location,
        url=url,
        description=description,
        posted_at=posted_at,
        raw=raw or {},
    )


def test_ingest_inserts_new_and_counts_duplicates_within_batch(session):
    raws = [
        make_raw("Globex", "Backend Engineer"),
        make_raw("Globex, Inc.", "Backend Engineer (Remote)"),
        make_raw("Initech", "QA Engineer"),
    ]

    stats = ingest(session, raws)

    assert (stats.fetched, stats.inserted, stats.duplicates) == (3, 2, 1)


def test_ingest_rejects_duplicate_against_db(session):
    ingest(session, [make_raw("Globex", "Backend Engineer")])

    stats = ingest(session, [make_raw("Globex LLC", "Backend Engineer")])

    assert stats.inserted == 0 and stats.duplicates == 1


def test_ingest_skips_invalid_entries(session):
    stats = ingest(
        session,
        [make_raw("", "Backend Engineer", url=""), make_raw("Globex", "Backend Engineer")],
    )

    assert stats.skipped == 1 and stats.inserted == 1


def test_collect_all_isolates_failing_source(session):
    class Broken:
        name = "broken"

        def fetch(self):
            raise CollectorError("HTTP 500")

    class Ok:
        name = "ok"

        def fetch(self):
            return [make_raw("Globex", "Backend Engineer")]

    results = collect_all(session, [Broken(), Ok()], get_settings())

    assert isinstance(results["broken"], IngestStats)
    assert results["broken"].errors and results["ok"].inserted == 1
