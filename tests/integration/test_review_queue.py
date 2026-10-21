from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from lookout.applications import get_application, transition_application
from lookout.matching import MatchDecision
from lookout.models import ApplicationEvent
from lookout.openings import get_opening
from lookout.routing import (
    InvalidReviewTransition,
    ReviewApplicationNotFoundError,
    approve_review,
    decline_review,
    expire_reviews,
    persist_decision,
)
from sqlmodel import select


def make_decision(lane: str, *, score: int | None = 88) -> MatchDecision:
    return MatchDecision(
        score=score,
        reasons=["Fictional Python experience matches"],
        red_flags=["Fictional schedule concern"],
        lane=lane,
    )


@pytest.mark.parametrize(
    ("lane", "status"),
    [
        ("auto_apply", "ready"),
        ("review", "awaiting_review"),
        ("manual_assist", "manual_assist"),
        ("rejected", "rejected"),
    ],
)
def test_persist_decision_initializes_every_lane_and_records_event(
    session, opening_fixture, lane, status
):
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

    application = persist_decision(
        session,
        opening_fixture,
        make_decision(lane),
        now=now,
    )
    event = session.exec(select(ApplicationEvent)).one()

    assert application.lane == lane
    assert application.status == status
    assert application.review_expires_at == (now + timedelta(days=7) if lane == "review" else None)
    assert event.event_type == "matching_decision"
    assert event.details == {"lane": lane, "score": 88}


def test_matching_rerun_does_not_extend_the_review_expiration(session, opening_fixture):
    first_run = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    application = persist_decision(
        session,
        opening_fixture,
        make_decision("review"),
        now=first_run,
    )

    rerun = persist_decision(
        session,
        opening_fixture,
        make_decision("review", score=89),
        now=first_run + timedelta(days=6),
    )

    assert rerun.id == application.id
    assert rerun.review_expires_at == first_run + timedelta(days=7)


def test_approve_review_moves_only_waiting_review_to_ready(session, opening_fixture):
    review = persist_decision(
        session,
        opening_fixture,
        make_decision("review"),
        now=datetime(2026, 10, 20, tzinfo=UTC),
    )
    session.commit()

    approved = approve_review(session, review.id)

    assert approved.lane == "auto_apply"
    assert approved.status == "ready"
    assert (
        session.exec(select(ApplicationEvent).order_by(ApplicationEvent.created_at))
        .all()[-1]
        .event_type
        == "review_approved"
    )


def test_decline_review_moves_to_manual_assist_and_records_action(session, opening_fixture):
    review = persist_decision(
        session,
        opening_fixture,
        make_decision("review"),
        now=datetime(2026, 10, 20, tzinfo=UTC),
    )

    declined = decline_review(session, review.id)
    event = session.exec(select(ApplicationEvent).order_by(ApplicationEvent.created_at)).all()[-1]

    assert declined.lane == "manual_assist"
    assert declined.status == "manual_assist"
    assert event.event_type == "review_declined"
    assert event.details == {"review_action": "declined"}


def test_approve_rejects_non_review_items_and_unknown_ids(session, opening_fixture):
    application = persist_decision(
        session,
        opening_fixture,
        make_decision("auto_apply", score=95),
    )

    with pytest.raises(InvalidReviewTransition):
        approve_review(session, application.id)
    with pytest.raises(ReviewApplicationNotFoundError):
        approve_review(session, uuid4())


def test_expire_reviews_respects_seven_day_boundary_and_keeps_source_url(session, opening_fixture):
    now = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    review = persist_decision(session, opening_fixture, make_decision("review"), now=now)
    expires_at = now + timedelta(days=7)

    assert expire_reviews(session, now=expires_at - timedelta(microseconds=1)) == 0
    assert get_application(session, review.id).status == "awaiting_review"
    assert expire_reviews(session, now=expires_at) == 1

    expired = get_application(session, review.id)
    source_opening = get_opening(session, opening_fixture.id)
    event = session.exec(select(ApplicationEvent).order_by(ApplicationEvent.created_at)).all()[-1]
    assert expired.lane == "manual_assist"
    assert expired.status == "expired"
    assert source_opening.url == "https://example.com/jobs/fixture-opening-1"
    assert event.event_type == "review_expired"
    assert expire_reviews(session, now=expires_at + timedelta(days=1)) == 0


def test_matching_rerun_does_not_reset_submitted_application(session, opening_fixture):
    application = persist_decision(
        session,
        opening_fixture,
        make_decision("auto_apply", score=96),
    )
    transition_application(
        session,
        application,
        lane="auto_apply",
        status="submitting",
        event_type="application_submitting",
    )
    transition_application(
        session,
        application,
        lane="auto_apply",
        status="submitted",
        event_type="application_submitted",
    )
    session.commit()

    rerun = persist_decision(
        session,
        get_opening(session, opening_fixture.id),
        make_decision("rejected", score=10),
    )

    assert rerun.status == "submitted"
    assert rerun.lane == "auto_apply"
    assert rerun.score == 96
    assert (
        session.exec(select(ApplicationEvent)).all()[-1].event_type == "matching_decision_ignored"
    )
