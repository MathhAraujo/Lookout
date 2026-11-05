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


def test_external_id_is_idempotent_when_posting_title_changes(session):
    ingest(session, [make_raw("Globex", "Backend Engineer", external_id="42")])
    stats = ingest(session, [make_raw("Globex", "QA Analyst", external_id="42")])
    assert stats.inserted == 0 and stats.duplicates == 1


def test_database_failure_rolls_back_only_its_source(session):
    from lookout.models import Opening
    from sqlmodel import select

    class Source:
        def __init__(self, name, raws):
            self.name, self.raws = name, raws

        def fetch(self):
            return self.raws

    broken = make_raw("Broken", "Developer", raw={"invalid": {1, 2}})
    results = collect_all(
        session,
        [
            Source("before", [make_raw("Before", "Developer")]),
            Source("broken", [make_raw("Partial", "Developer"), broken]),
            Source("after", [make_raw("After", "Developer")]),
        ],
        get_settings(),
    )
    session.commit()
    assert results["before"].inserted == results["after"].inserted == 1
    assert results["broken"].errors
    assert {row.company for row in session.exec(select(Opening))} == {"Before", "After"}
    assert "invalid" not in results["broken"].errors[0]


def test_concurrent_cross_source_ingestion_inserts_only_once(session, engine):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event

    from lookout.models import Opening
    from sqlmodel import Session, select

    first = ingest(session, [make_raw("Globex", "Engineer", source="one")])
    started = Event()

    def second_ingest():
        with Session(engine) as other:
            started.set()
            stats = ingest(other, [make_raw("Globex", "Engineer", source="two")])
            other.commit()
            return stats

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(second_ingest)
        try:
            assert started.wait(timeout=5)
            # The second writer must wait for the first transaction's decision.
            try:
                future.result(timeout=0.25)
            except TimeoutError:
                pass
            else:
                raise AssertionError("Concurrent writer did not wait for the ingestion lock")
        finally:
            session.commit()
        second = future.result(timeout=5)
    assert first.inserted == 1
    assert second.inserted == 0 and second.duplicates == 1
    assert len(session.exec(select(Opening)).all()) == 1
