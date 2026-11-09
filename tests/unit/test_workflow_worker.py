"""Queue integration, opt-in collection, and independent maintenance checks."""

from types import SimpleNamespace

from lookout.collectors.base import RawOpening
from lookout.config import Settings
from lookout.ingest import collect_source
from lookout.models import Application, ConnectorHealth, Job
from lookout.queue import enqueue
from lookout.worker import JOB_HANDLERS, process_next_job
from sqlmodel import select


def test_worker_registers_matching_and_application_jobs():
    assert {"match", "apply"} <= JOB_HANDLERS.keys()


def test_collection_enqueues_only_new_openings_when_workflow_is_enabled(session):
    class Source:
        def fetch(self):
            return [
                RawOpening(
                    "remoteok",
                    "new",
                    "Fictional",
                    "Python",
                    None,
                    "https://example.com/jobs/new",
                    "Build Python APIs",
                    None,
                    {},
                )
            ]

    settings = Settings(workflow_enabled=True)
    first = collect_source(session, Source(), settings)
    second = collect_source(session, Source(), settings)
    jobs = list(session.exec(select(Job)).all())
    assert len(jobs) == 1
    assert jobs[0].type == "match"
    assert jobs[0].payload == {"opening_id": str(first.inserted_ids[0])}
    assert second.inserted_ids == []


def test_backfill_is_idempotent_and_skips_existing_decisions(session, opening_fixture):
    from lookout.workflow import enqueue_backfill

    assert enqueue_backfill(session) == 1
    assert enqueue_backfill(session) == 0
    application = Application(opening_id=opening_fixture.id, lane="auto_apply", status="submitted")
    session.add(application)
    session.flush()
    assert enqueue_backfill(session) == 0
    assert application.status == "submitted"


def test_connector_failure_does_not_stop_other_checks_or_queue(session, settings, monkeypatch):
    from lookout.connector_health import ConnectorHealthSnapshot, refresh_connector_health

    def check(platform, **kwargs):
        if platform == "greenhouse":
            raise RuntimeError("fictional-private-payload")
        return ConnectorHealthSnapshot(platform, "healthy", "browser_session_healthy", None)

    monkeypatch.setattr("lookout.connector_health.check_connector_health", check)
    refresh_connector_health(session, settings)
    states = {item.connector: item.status for item in session.exec(select(ConnectorHealth))}
    assert states == {"greenhouse": "unavailable", "lever": "healthy", "email": "healthy"}
    job = enqueue(session, "fixture", {})
    monkeypatch.setitem(JOB_HANDLERS, "fixture", lambda *args: None)
    assert process_next_job(session, settings)
    session.refresh(job)
    assert job.status == "done"


def test_scheduler_registers_review_expiry_and_daily_connector_checks(monkeypatch):
    from lookout import worker

    jobs = []
    scheduler = SimpleNamespace(
        add_job=lambda *args, **kwargs: jobs.append(kwargs),
        start=lambda: None,
        shutdown=lambda **kwargs: None,
    )
    monkeypatch.setattr(worker, "BackgroundScheduler", lambda: scheduler)
    monkeypatch.setattr(worker, "get_settings", lambda: Settings(workflow_enabled=True))
    monkeypatch.setattr(worker, "load_sources_config", lambda path: {})
    monkeypatch.setattr(
        worker.threading,
        "Event",
        lambda: SimpleNamespace(wait=lambda: (_ for _ in ()).throw(KeyboardInterrupt())),
    )
    worker.main()
    scheduled = {job["id"]: job for job in jobs}
    assert scheduled["expire-reviews"]["hours"] == 1
    assert scheduled["check-connectors"]["days"] == 1
