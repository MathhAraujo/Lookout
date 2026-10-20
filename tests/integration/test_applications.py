from datetime import UTC, datetime
from uuid import uuid4

import pytest
from lookout.applications import (
    get_application,
    list_applications,
    transition_application,
    upsert_application,
)
from lookout.collectors.base import RawOpening
from lookout.models import (
    Application,
    ApplicationAnswer,
    ApplicationArtifact,
    ApplicationEvent,
    ConnectorHealth,
)
from lookout.openings import insert_opening
from sqlalchemy.exc import IntegrityError
from sqlmodel import select


def make_raw_opening(*, application_email: str | None = None) -> RawOpening:
    return RawOpening(
        source="greenhouse",
        external_id="fictional-opening-42",
        company="Globex",
        title="Backend Engineer",
        location="Remote",
        url="https://example.com/jobs/fictional-opening-42",
        description="Build fictional internal services.",
        posted_at=None,
        raw={},
        application_email=application_email,
    )


def test_insert_opening_persists_only_explicit_application_email(session):
    opening = insert_opening(
        session,
        make_raw_opening(application_email="apply@example.com"),
    )

    assert opening.application_email == "apply@example.com"


def test_upsert_keeps_one_application_per_opening_and_json_decision_fields(
    session, opening_fixture
):
    first = upsert_application(
        session,
        opening_fixture.id,
        lane="review",
        status="awaiting_review",
        score=84,
        reasons=["Matches Python requirement"],
        red_flags=["Salary range not listed"],
    )
    second = upsert_application(
        session,
        opening_fixture.id,
        lane="rejected",
        status="rejected",
        score=42,
        reasons=["Role is below the target level"],
        red_flags=[],
    )

    assert second.id == first.id
    assert second.lane == "rejected"
    assert second.score == 42
    assert second.reasons == ["Role is below the target level"]
    assert second.red_flags == []
    assert len(list_applications(session)) == 1
    assert list_applications(session, lane="rejected") == [second]
    assert get_application(session, first.id).id == first.id


def test_matching_rerun_does_not_change_submitted_application(session, opening_fixture):
    submitted_at = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    application = upsert_application(
        session,
        opening_fixture.id,
        lane="auto_apply",
        status="submitted",
        score=96,
        reasons=["Strong match"],
        red_flags=[],
    )
    application.submitted_at = submitted_at
    session.commit()

    rerun = upsert_application(
        session,
        opening_fixture.id,
        lane="rejected",
        status="rejected",
        score=20,
        reasons=["Changed scoring result"],
        red_flags=["Changed flag"],
    )

    assert rerun.status == "submitted"
    assert rerun.lane == "auto_apply"
    assert rerun.score == 96
    assert rerun.submitted_at == submitted_at


def test_database_rejects_duplicate_application_for_an_opening(session, opening_fixture):
    upsert_application(
        session,
        opening_fixture.id,
        lane="auto_apply",
        status="ready",
        score=93,
        reasons=[],
        red_flags=[],
    )
    duplicate = Application(
        opening_id=opening_fixture.id,
        lane="review",
        status="awaiting_review",
        score=75,
        reasons=[],
        red_flags=[],
        dry_run=True,
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.flush()


def test_transition_updates_status_and_event_in_one_transaction(session, opening_fixture):
    application = upsert_application(
        session,
        opening_fixture.id,
        lane="review",
        status="awaiting_review",
        score=78,
        reasons=["Borderline match"],
        red_flags=[],
    )
    session.commit()

    transition_application(
        session,
        application,
        lane="auto_apply",
        status="ready",
        event_type="review_approved",
        details={
            "review_action": "approved",
            "answer_text": "fictional answer must not persist",
            "password": "fictional secret must not persist",
        },
    )
    session.rollback()
    session.expire_all()

    assert get_application(session, application.id).status == "awaiting_review"
    assert session.exec(select(ApplicationEvent)).all() == []

    transition_application(
        session,
        get_application(session, application.id),
        lane="auto_apply",
        status="ready",
        event_type="review_approved",
        details={
            "review_action": "approved",
            "answer_text": "fictional answer must not persist",
            "password": "fictional secret must not persist",
        },
    )
    session.commit()

    saved = get_application(session, application.id)
    event = session.exec(select(ApplicationEvent)).one()
    assert saved.status == "ready"
    assert event.event_type == "review_approved"
    assert event.details == {"review_action": "approved"}


def test_submitted_application_cannot_transition_back_to_ready(session, opening_fixture):
    application = upsert_application(
        session,
        opening_fixture.id,
        lane="auto_apply",
        status="submitted",
        score=94,
        reasons=[],
        red_flags=[],
    )

    with pytest.raises(ValueError, match="invalid application transition"):
        transition_application(
            session,
            application,
            lane="auto_apply",
            status="ready",
            event_type="matching_rerun",
        )

    assert application.status == "submitted"
    assert session.exec(select(ApplicationEvent)).all() == []


def test_invalid_event_details_do_not_mutate_application(session, opening_fixture):
    application = upsert_application(
        session,
        opening_fixture.id,
        lane="review",
        status="awaiting_review",
        score=78,
        reasons=["Borderline match"],
        red_flags=[],
    )
    session.commit()

    with pytest.raises(TypeError, match="event details must be a mapping"):
        transition_application(
            session,
            application,
            lane="auto_apply",
            status="ready",
            event_type="review_approved",
            details="not a mapping",
        )

    session.commit()
    session.refresh(application)
    assert application.status == "awaiting_review"
    assert session.exec(select(ApplicationEvent)).all() == []


def test_application_children_and_connector_health_persist_without_answer_text(
    session, opening_fixture
):
    application = upsert_application(
        session,
        opening_fixture.id,
        lane="manual_assist",
        status="manual_assist",
        score=74,
        reasons=["Target requires manual review"],
        red_flags=[],
    )
    answer = ApplicationAnswer(
        application_id=application.id,
        question_key="unknown_optional",
        source="unresolved",
        status="skipped",
    )
    artifact = ApplicationArtifact(
        application_id=application.id,
        kind="resume",
        object_key=f"applications/{application.id}/resume",
        content_type="application/pdf",
        sha256="a" * 64,
    )
    event = ApplicationEvent(
        application_id=application.id,
        event_type="screened",
        details={"result": "optional_question_skipped"},
    )
    health = ConnectorHealth(
        connector="greenhouse",
        status="healthy",
        detail="Connector available",
    )
    session.add_all([answer, artifact, event, health])
    session.commit()

    assert session.get(ApplicationAnswer, answer.id).status == "skipped"
    assert session.get(ApplicationArtifact, artifact.id).object_key == artifact.object_key
    assert session.get(ApplicationEvent, event.id).details == {
        "result": "optional_question_skipped"
    }
    assert session.get(ConnectorHealth, health.id).connector == "greenhouse"
    assert "answer" not in ApplicationAnswer.__table__.columns
    assert "answer_text" not in ApplicationEvent.__table__.columns


def test_application_answer_requires_an_existing_application(session):
    session.add(
        ApplicationAnswer(
            application_id=uuid4(),
            question_key="work_authorization",
            source="fact",
            status="answered",
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()
