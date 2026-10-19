from datetime import timedelta

from lookout.db import utcnow
from lookout.queue import claim_next, enqueue, fail, reap_stale
from sqlmodel import Session


def test_claim_next_picks_oldest_due_job(session):
    enqueue(session, "collect", {"source": "later"}, run_at=utcnow() + timedelta(hours=1))
    first = enqueue(session, "collect", {"source": "now"})

    claimed = claim_next(session)

    assert claimed is not None
    assert claimed.id == first.id and claimed.status == "running" and claimed.attempts == 1
    assert claim_next(session) is None


def test_claim_next_skips_locked_rows(session, engine):
    enqueue(session, "collect", {"source": "a"})
    enqueue(session, "collect", {"source": "b"})
    session.commit()

    with Session(engine) as tx2:
        first = claim_next(session)
        assert first is not None and first.payload["source"] == "a"
        second = claim_next(tx2)
        assert second is not None and second.payload["source"] == "b"


def test_fail_requeues_with_backoff_then_gives_up(session):
    job = enqueue(session, "collect", {"source": "x"}, max_attempts=2)
    assert claim_next(session) is not None

    fail(session, job, "boom")

    assert job.status == "pending" and job.run_at > utcnow() and job.last_error == "boom"
    assert claim_next(session, now=utcnow() + timedelta(minutes=3)) is not None
    fail(session, job, "boom again")

    assert job.status == "failed"


def test_reap_stale_returns_crashed_jobs_to_pending(session):
    job = enqueue(session, "collect", {"source": "x"})
    assert claim_next(session) is not None
    job.updated_at = utcnow() - timedelta(hours=1)
    session.add(job)
    session.commit()

    assert reap_stale(session) == 1
    session.refresh(job)
    assert job.status == "pending"
