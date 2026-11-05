from datetime import datetime, timedelta

from sqlalchemy import update
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
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
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
        .where(Job.status == "pending", Job.run_at <= claimed_at, Job.attempts < Job.max_attempts)
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


def reap_stale(session: Session, *, stale_after: timedelta = timedelta(minutes=30)) -> int:
    now = utcnow()
    stale_before = now - stale_after
    statement = (
        select(Job)
        .where(Job.status == "running", Job.updated_at < stale_before)
        .with_for_update(skip_locked=True)
    )
    stale_jobs = list(session.exec(statement).all())

    for job in stale_jobs:
        job.status = "failed" if job.attempts >= job.max_attempts else "pending"
        job.last_error = "Worker lease expired"
        job.updated_at = now
        session.add(job)

    session.flush()
    return len(stale_jobs)


def heartbeat(session: Session, job_id, attempt: int) -> bool:
    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "running", Job.attempts == attempt)
        .values(updated_at=utcnow())
    )
    return result.rowcount == 1


def owned_job(session: Session, job_id, attempt: int) -> Job | None:
    return session.exec(
        select(Job)
        .where(Job.id == job_id, Job.status == "running", Job.attempts == attempt)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
