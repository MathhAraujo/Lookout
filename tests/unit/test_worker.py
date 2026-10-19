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

    assert job.status == "failed" and "collector exploded" in job.last_error
