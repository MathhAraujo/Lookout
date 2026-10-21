from datetime import datetime, timedelta
from uuid import UUID

from sqlmodel import Session, select

from lookout.applications import (
    get_application,
    record_application_event,
    transition_application,
    upsert_application,
)
from lookout.db import utcnow
from lookout.matching import MatchDecision, MatchLane
from lookout.models import Application, Opening

_INITIAL_STATUS_BY_LANE = {
    "auto_apply": "ready",
    "review": "awaiting_review",
    "manual_assist": "manual_assist",
    "rejected": "rejected",
}


class ReviewApplicationNotFoundError(Exception):
    """Raised when a requested application does not exist."""


class InvalidReviewTransition(ValueError):
    """Raised when a review action is invalid for an application state."""


def initial_status_for_lane(lane: MatchLane) -> str:
    try:
        return _INITIAL_STATUS_BY_LANE[lane]
    except KeyError:
        raise ValueError("unknown application lane") from None


def review_expiration_for_lane(lane: MatchLane, now: datetime | None = None) -> datetime | None:
    if lane != "review":
        return None
    return (now or utcnow()) + timedelta(days=7)


def persist_decision(
    session: Session,
    opening: Opening,
    decision: MatchDecision,
    *,
    now: datetime | None = None,
) -> Application:
    decision_time = now or utcnow()
    status = initial_status_for_lane(decision.lane)
    review_expires_at = review_expiration_for_lane(decision.lane, decision_time)
    existing = session.exec(select(Application).where(Application.opening_id == opening.id)).first()
    if (
        existing is not None
        and existing.lane == "review"
        and existing.status == "awaiting_review"
        and decision.lane == "review"
        and existing.review_expires_at is not None
    ):
        review_expires_at = existing.review_expires_at

    application = upsert_application(
        session,
        opening.id,
        lane=decision.lane,
        status=status,
        score=decision.score,
        reasons=decision.reasons,
        red_flags=decision.red_flags,
        review_expires_at=review_expires_at,
    )
    record_application_event(
        session,
        application.id,
        event_type=(
            "matching_decision_ignored"
            if existing is not None and existing.status == "submitted"
            else "matching_decision"
        ),
        details={"lane": decision.lane, "score": decision.score},
    )
    return application


def _get_waiting_review(session: Session, application_id: UUID) -> Application:
    application = get_application(session, application_id)
    if application is None:
        raise ReviewApplicationNotFoundError("application not found")
    if application.lane != "review" or application.status != "awaiting_review":
        raise InvalidReviewTransition("application is not awaiting review")
    return application


def approve_review(session: Session, application_id: UUID) -> Application:
    application = _get_waiting_review(session, application_id)
    try:
        return transition_application(
            session,
            application,
            lane="auto_apply",
            status="ready",
            event_type="review_approved",
            details={"review_action": "approved"},
        )
    except ValueError as error:
        raise InvalidReviewTransition("application cannot be approved") from error


def decline_review(session: Session, application_id: UUID) -> Application:
    application = _get_waiting_review(session, application_id)
    try:
        return transition_application(
            session,
            application,
            lane="manual_assist",
            status="manual_assist",
            event_type="review_declined",
            details={"review_action": "declined"},
        )
    except ValueError as error:
        raise InvalidReviewTransition("application cannot be declined") from error


def expire_reviews(session: Session, *, now: datetime | None = None) -> int:
    expiration_time = now or utcnow()
    statement = select(Application).where(
        Application.lane == "review",
        Application.status == "awaiting_review",
        Application.review_expires_at <= expiration_time,
    )
    applications = list(session.exec(statement).all())

    for application in applications:
        transition_application(
            session,
            application,
            lane="manual_assist",
            status="expired",
            event_type="review_expired",
            details={"review_action": "expired"},
        )
    return len(applications)
