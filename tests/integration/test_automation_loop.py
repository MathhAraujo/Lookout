"""Real PostgreSQL workflow, PDF rendering, and HTTP-stubbed OpenRouter responses."""

from datetime import timedelta

import pytest
from lookout.appliers import ApplicationForm, ApplyResult
from lookout.db import utcnow
from lookout.models import Application, ApplicationAnswer, ApplicationArtifact, Job, Opening
from lookout.queue import enqueue, reap_stale
from lookout.screener import FormQuestion
from lookout.worker import process_next_job
from sqlmodel import select

from tests.workflow_helpers import configure_workflow


@pytest.mark.parametrize(
    "source,title,want_lane,want_status,want_artifacts",
    [
        ("greenhouse", "Senior Python Engineer", "auto_apply", "dry_run", 3),
        ("greenhouse", "Review Senior Python Engineer", "review", "awaiting_review", 2),
        ("remoteok", "Senior Python Engineer", "manual_assist", "manual_assist", 2),
        ("greenhouse", "Reject Senior Python Engineer", "rejected", "rejected", 0),
    ],
)
def test_matching_prepares_each_eligible_lane_only(
    session, engine, tmp_path, monkeypatch, source, title, want_lane, want_status, want_artifacts
):
    settings, store, prompts = configure_workflow(monkeypatch, tmp_path, engine)
    opening = Opening(
        source=source,
        external_id="fictional",
        company="Fictional",
        title=title,
        location="Remote",
        url="https://example.com/job",
        description="Build Python APIs with our remote team.",
        dedup_key="fictional",
    )
    session.add(opening)
    session.flush()

    class Applier:
        def inspect(self, *args, **kwargs):
            assert want_lane == "auto_apply"
            return ApplicationForm(
                [
                    FormQuestion("email", "Email address", True),
                    FormQuestion("years", "How many years of experience?", True),
                ]
            )

        def submit(self, application, opening, *, dry_run, answers, **kwargs):
            assert dry_run is True
            assert {answer.key: answer.answer for answer in answers} == {
                "email": "maria.silva@example.com",
                "years": "5",
            }
            return ApplyResult("dry_run", "dry_run_fill_succeeded")

    monkeypatch.setattr("lookout.workflow.build_applier", lambda *args: Applier())
    enqueue(session, "match", {"opening_id": str(opening.id)})
    for _ in range(3):
        process_next_job(session, settings)
    application = session.exec(select(Application)).one()
    assert (application.lane, application.status) == (want_lane, want_status)
    artifacts = list(session.exec(select(ApplicationArtifact)))
    assert len(artifacts) == want_artifacts
    for artifact in artifacts:
        content = store.get_bytes(artifact.object_key)
        if artifact.kind == "resume":
            assert content.startswith(b"%PDF")
    assert all(job.status == "done" for job in session.exec(select(Job)))
    assert len(prompts) == (1 if want_lane == "rejected" else 2)


def test_unknown_required_question_blocks_before_submit(
    session, engine, tmp_path, monkeypatch, opening_fixture
):
    from lookout.matching import MatchDecision
    from lookout.routing import persist_decision

    settings, _store, _ = configure_workflow(monkeypatch, tmp_path, engine)
    application = persist_decision(
        session, opening_fixture, MatchDecision(95, [], [], "auto_apply")
    )

    class Applier:
        def inspect(self, *args, **kwargs):
            return ApplicationForm(
                [FormQuestion("unknown", "Unrecognized required question", True)]
            )

        def submit(self, *args, **kwargs):
            pytest.fail("blocked applications must never submit")

    monkeypatch.setattr("lookout.workflow.build_applier", lambda *args: Applier())
    enqueue(session, "apply", {"application_id": str(application.id)})
    process_next_job(session, settings)
    session.refresh(application)
    assert (application.lane, application.status) == ("manual_assist", "blocked")
    assert session.exec(select(ApplicationAnswer)).one().status == "blocked"


def test_crash_after_submit_is_not_replayed_after_stale_recovery(
    session, engine, tmp_path, monkeypatch, opening_fixture
):
    from lookout.matching import MatchDecision
    from lookout.routing import persist_decision

    settings, _, _ = configure_workflow(monkeypatch, tmp_path, engine)
    settings.dry_run = False
    settings.auto_submit_enabled = True
    application = persist_decision(
        session, opening_fixture, MatchDecision(95, [], [], "auto_apply")
    )
    application_id = application.id
    calls = []

    class Crash(BaseException):
        pass

    class Applier:
        def inspect(self, *args, **kwargs):
            return ApplicationForm([])

        def submit(self, application, *args, **kwargs):
            with type(session)(engine) as observer:
                assert observer.get(Application, application_id).status == "submitting"
            calls.append("sent")
            raise Crash()

    monkeypatch.setattr("lookout.workflow.build_applier", lambda *args: Applier())
    job = enqueue(session, "apply", {"application_id": str(application_id)})
    with pytest.raises(Crash):
        process_next_job(session, settings)
    session.rollback()
    session.refresh(job)
    job.updated_at = utcnow() - timedelta(hours=1)
    session.commit()
    assert reap_stale(session) == 1
    session.commit()
    assert process_next_job(session, settings)
    session.refresh(application)
    assert (application.lane, application.status) == ("manual_assist", "manual_assist")
    assert calls == ["sent"]
    enqueue(session, "apply", {"application_id": str(application_id)})
    process_next_job(session, settings)
    assert calls == ["sent"]


def test_final_record_upload_retries_without_repeating_submission(
    session, engine, tmp_path, monkeypatch, opening_fixture
):
    from lookout.artifacts import ArtifactStoreError
    from lookout.matching import MatchDecision
    from lookout.routing import persist_decision
    from lookout.workflow import apply_application

    settings, store, _ = configure_workflow(monkeypatch, tmp_path, engine)
    settings.dry_run = False
    settings.auto_submit_enabled = True
    application = persist_decision(
        session, opening_fixture, MatchDecision(95, [], [], "auto_apply")
    )
    calls = []

    class Applier:
        def inspect(self, *args, **kwargs):
            return ApplicationForm([])

        def submit(self, *args, **kwargs):
            calls.append("sent")
            return ApplyResult("submitted", "submission_confirmed")

    monkeypatch.setattr("lookout.workflow.build_applier", lambda *args: Applier())
    upload = store.put_file

    def fail_record(**kwargs):
        if kwargs["key"].endswith("/opening_record"):
            raise ArtifactStoreError("temporary artifact outage")
        return upload(**kwargs)

    monkeypatch.setattr(store, "put_file", fail_record)
    with pytest.raises(ArtifactStoreError):
        apply_application(session, settings, application.id)
    session.rollback()
    assert session.get(Application, application.id).status == "submitted"
    monkeypatch.setattr(store, "put_file", upload)
    apply_application(session, settings, application.id)
    assert calls == ["sent"]
    record = session.exec(
        select(ApplicationArtifact).where(ApplicationArtifact.kind == "opening_record")
    ).one()
    import json

    assert json.loads(store.get_bytes(record.object_key))["status"] == "submitted"


def test_submitted_application_never_generates_or_submits_again(
    session, engine, tmp_path, monkeypatch, opening_fixture
):
    from lookout.workflow import apply_application

    settings, _, prompts = configure_workflow(monkeypatch, tmp_path, engine)
    application = Application(opening_id=opening_fixture.id, lane="auto_apply", status="submitted")
    session.add(application)
    session.commit()
    apply_application(session, settings, application.id)
    assert prompts == []
    assert list(session.exec(select(ApplicationArtifact))) == []


@pytest.mark.parametrize("dry_run,enabled", [(True, False), (True, True), (False, False)])
def test_either_disabled_submit_flag_uses_actual_email_adapter_without_smtp(
    session, engine, tmp_path, monkeypatch, opening_fixture, dry_run, enabled
):
    from lookout.matching import MatchDecision
    from lookout.routing import persist_decision

    settings, _, _ = configure_workflow(monkeypatch, tmp_path, engine)
    settings.dry_run = dry_run
    settings.auto_submit_enabled = enabled
    opening_fixture.application_email = "apply@fictional.example"
    application = persist_decision(
        session, opening_fixture, MatchDecision(95, [], [], "auto_apply")
    )
    enqueue(session, "apply", {"application_id": str(application.id)})
    assert process_next_job(session, settings)
    session.refresh(application)
    assert application.status == "dry_run"
    assert application.dry_run is True


def test_active_application_guard_retries_contending_job(
    session, engine, tmp_path, monkeypatch, opening_fixture
):
    from lookout.matching import MatchDecision
    from lookout.routing import persist_decision
    from sqlalchemy import text

    settings, _, _ = configure_workflow(monkeypatch, tmp_path, engine)
    opening_fixture.application_email = "apply@fictional.example"
    application = persist_decision(
        session, opening_fixture, MatchDecision(95, [], [], "auto_apply")
    )
    job = enqueue(session, "apply", {"application_id": str(application.id)})
    session.commit()
    key = application.id.int & ((1 << 63) - 1)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as owner:
        owner.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
        try:
            assert process_next_job(session, settings)
            session.refresh(job)
            assert job.status == "pending"
            assert session.get(Application, application.id).status == "ready"
        finally:
            owner.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    job.run_at = utcnow()
    session.commit()
    assert process_next_job(session, settings)
    session.refresh(application)
    assert application.status == "dry_run"


def test_reclaimed_worker_lease_prevents_submission(
    session, engine, tmp_path, monkeypatch, opening_fixture
):
    from lookout.matching import MatchDecision
    from lookout.routing import persist_decision

    settings, _, _ = configure_workflow(monkeypatch, tmp_path, engine)
    settings.dry_run = False
    settings.auto_submit_enabled = True
    application = persist_decision(
        session, opening_fixture, MatchDecision(95, [], [], "auto_apply")
    )
    job = enqueue(session, "apply", {"application_id": str(application.id)})
    job_id = job.id

    class Applier:
        def inspect(self, *args, **kwargs):
            with type(session)(engine) as observer:
                stolen = observer.get(Job, job_id)
                stolen.attempts += 1
                observer.commit()
            return ApplicationForm([])

        def submit(self, *args, **kwargs):
            pytest.fail("an obsolete worker must never submit")

    monkeypatch.setattr("lookout.workflow.build_applier", lambda *args: Applier())
    assert process_next_job(session, settings)
    session.refresh(application)
    assert application.status == "ready"


def test_connector_inspection_preserves_safe_failure_reason(
    session, engine, tmp_path, monkeypatch, opening_fixture
):
    from lookout.appliers import ApplierError
    from lookout.matching import MatchDecision
    from lookout.routing import persist_decision

    settings, _, _ = configure_workflow(monkeypatch, tmp_path, engine)
    application = persist_decision(
        session, opening_fixture, MatchDecision(95, [], [], "auto_apply")
    )

    class Applier:
        def inspect(self, *args, **kwargs):
            raise ApplierError("browser_session_expired")

    monkeypatch.setattr("lookout.workflow.build_applier", lambda *args: Applier())
    enqueue(session, "apply", {"application_id": str(application.id)})
    process_next_job(session, settings)
    session.refresh(application)
    assert (application.lane, application.status) == ("manual_assist", "manual_assist")
    assert application.last_error == "browser_session_expired"


@pytest.mark.parametrize(
    "platform,filename", [("greenhouse", "greenhouse_form.html"), ("lever", "lever_posting.html")]
)
def test_api_to_real_browser_dry_run_and_artifact_download(
    session, engine, tmp_path, monkeypatch, platform, filename
):
    import http.server
    import io
    import threading
    from pathlib import Path
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from lookout.api import create_app, get_session
    from lookout.collectors.base import RawOpening
    from pypdf import PdfReader

    from tests.unit.appliers.conftest import _Handler

    settings, store, _ = configure_workflow(monkeypatch, tmp_path, engine)
    facts = tmp_path / "facts.yml"
    facts.write_text(settings.facts_path.read_text().replace('"Yes"', '"Yes, authorized"'))
    settings.facts_path = facts
    settings.browser_profiles_path = tmp_path / "profiles"
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.root = Path("tests/fixtures/appliers").resolve()
    server.recorder = SimpleNamespace(submission_posts=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/{filename}"

    class Source:
        def fetch(self):
            return [
                RawOpening(
                    platform,
                    "browser-flow",
                    "Fictional Sciences",
                    "Senior Python Engineer",
                    "Remote",
                    url,
                    "Build Python APIs with our remote team.",
                    None,
                    {},
                )
            ]

    monkeypatch.setattr("lookout.worker.get_collector", lambda *args: Source())
    monkeypatch.setattr("lookout.api.build_artifact_store", lambda settings: store)
    app = create_app(settings)
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            for _ in range(2):
                assert client.post("/collect", json={"source": platform}).status_code == 202
            for _ in range(8):
                if not process_next_job(session, settings):
                    break
            application = session.exec(select(Application)).one()
            assert application.status == "dry_run"
            assert server.recorder.submission_posts == 0
            artifacts = client.get(f"/applications/{application.id}/artifacts").json()
            resume = next(item for item in artifacts if item["kind"] == "resume")
            response = client.get(f"/artifacts/{resume['id']}")
            pdf = PdfReader(io.BytesIO(response.content))
            assert "Maria Silva" in pdf.pages[0].extract_text()
            assert all(job.status == "done" for job in session.exec(select(Job)))
            assert all(
                "answer" not in row.model_dump() for row in session.exec(select(ApplicationAnswer))
            )
    finally:
        app.state.engine.dispose()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
