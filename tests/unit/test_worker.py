from lookout.queue import enqueue
from lookout.worker import JOB_HANDLERS, process_next_job


def test_process_next_job_dispatches_and_completes(session, settings, monkeypatch):
    job = enqueue(session, "collect", {"source": "fake"})
    monkeypatch.setitem(JOB_HANDLERS, "collect", lambda session, settings, payload: None)

    assert process_next_job(session, settings) is True
    session.refresh(job)
    assert job.status == "done"


def test_process_next_job_marks_failure(session, settings, monkeypatch):
    job = enqueue(session, "collect", {"source": "fake"}, max_attempts=1)

    def boom(session, settings, payload):
        raise RuntimeError("collector exploded")

    monkeypatch.setitem(JOB_HANDLERS, "collect", boom)
    process_next_job(session, settings)
    session.refresh(job)

    assert job.status == "failed" and job.last_error == "Job failed (RuntimeError)"


def test_collect_all_job_fans_out_to_independent_source_jobs(session, settings, monkeypatch):
    from types import SimpleNamespace

    from lookout.models import Job
    from lookout.worker import handle_collect
    from sqlmodel import select

    monkeypatch.setattr("lookout.worker.load_sources_config", lambda path: {})
    monkeypatch.setattr(
        "lookout.worker.build_collectors",
        lambda settings, sources: [SimpleNamespace(name="one"), SimpleNamespace(name="two")],
    )
    handle_collect(session, settings, {})
    assert {job.payload["source"] for job in session.exec(select(Job))} == {"one", "two"}
