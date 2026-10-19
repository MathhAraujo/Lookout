from datetime import datetime, timedelta

from sqlmodel import Session, select

from lookout.db import utcnow
from lookout.models import Job


def enqueue(
    session: Session,
    job_type: str,
    payload: dict,
    *,
    run_at: datetime | None = None,
    max_attempts: int = 3,
) -> Job:
    job = Job(
        type=job_type,
        payload=payload,
        run_at=run_at or utcnow(),
        max_attempts=max_attempts,
    )
    session.add(job)
    session.flush()
    return job


def claim_next(session: Session, *, now: datetime | None = None) -> Job | None:
    claimed_at = now or utcnow()
    statement = (
        select(Job)
        .where(Job.status == "pending", Job.run_at <= claimed_at)
        .order_by(Job.created_at, Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.exec(statement).first()

    if job is None:
        return None

    job.status = "running"
    job.attempts += 1
    job.updated_at = claimed_at
    session.add(job)
    session.flush()
    return job


def complete(session: Session, job: Job) -> None:
    job.status = "done"
    job.updated_at = utcnow()
    session.add(job)
    session.flush()


def fail(session: Session, job: Job, error: str) -> None:
    now = utcnow()
    job.last_error = error
    job.updated_at = now

    if job.attempts >= job.max_attempts:
        job.status = "failed"
    else:
        job.status = "pending"
        job.run_at = now + timedelta(minutes=2**job.attempts)

    session.add(job)
    session.flush()


def reap_stale(
    session: Session, *, stale_after: timedelta = timedelta(minutes=30)
) -> int:
    now = utcnow()
    stale_before = now - stale_after
    statement = (
        select(Job)
        .where(Job.status == "running", Job.updated_at < stale_before)
        .with_for_update(skip_locked=True)
    )
    stale_jobs = list(session.exec(statement).all())

    for job in stale_jobs:
        job.status = "pending"
        job.updated_at = now
        session.add(job)

    session.flush()
    return len(stale_jobs)
