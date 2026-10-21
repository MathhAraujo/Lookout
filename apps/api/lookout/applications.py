from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlmodel import Session, select

from lookout.db import utcnow
from lookout.models import Application, ApplicationEvent

ApplicationLane = Literal["auto_apply", "review", "manual_assist", "rejected"]
ApplicationStatus = Literal[
    "awaiting_review",
    "ready",
    "manual_assist",
    "rejected",
    "blocked",
    "dry_run",
    "submitting",
    "submitted",
    "expired",
]

_VALID_STATUSES_BY_LANE: dict[str, set[str]] = {
    "auto_apply": {"ready", "dry_run", "submitting", "submitted"},
    "review": {"awaiting_review"},
    "manual_assist": {"manual_assist", "blocked", "expired"},
    "rejected": {"rejected"},
}
_ALLOWED_TRANSITIONS: set[tuple[str, str]] = {
    ("awaiting_review", "ready"),
    ("awaiting_review", "manual_assist"),
    ("awaiting_review", "expired"),
    ("ready", "submitting"),
    ("ready", "dry_run"),
    ("ready", "blocked"),
    ("ready", "manual_assist"),
    ("submitting", "submitted"),
    ("submitting", "manual_assist"),
}
_SENSITIVE_DETAIL_TERMS = (
    "answer",
    "credential",
    "password",
    "secret",
    "token",
    "payload",
    "email",
    "phone",
    "address",
    "cpf",
    "personal",
)


def _validate_decision(lane: str, status: str, score: int | None) -> None:
    if status not in _VALID_STATUSES_BY_LANE.get(lane, set()):
        raise ValueError(f"status {status!r} is not valid for lane {lane!r}")
    if score is not None and (isinstance(score, bool) or not 0 <= score <= 100):
        raise ValueError("score must be between 0 and 100")


def _sanitize_event_details(details: dict | None) -> dict:
    if details is None:
        return {}
    if not isinstance(details, dict):
        raise TypeError("event details must be a mapping")

    def sanitize(value):
        if isinstance(value, dict):
            return {
                str(key): sanitize(item)
                for key, item in value.items()
                if not any(term in str(key).casefold() for term in _SENSITIVE_DETAIL_TERMS)
            }
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError("event details must contain JSON-compatible values")

    return sanitize(details)


def record_application_event(
    session: Session,
    application_id: UUID,
    *,
    event_type: str,
    details: dict | None = None,
) -> ApplicationEvent:
    if not event_type.strip():
        raise ValueError("event type is required")
    event = ApplicationEvent(
        application_id=application_id,
        event_type=event_type,
        details=_sanitize_event_details(details),
    )
    session.add(event)
    session.flush()
    return event


def upsert_application(
    session: Session,
    opening_id: UUID,
    *,
    lane: ApplicationLane,
    status: ApplicationStatus,
    score: int | None,
    reasons: list[str],
    red_flags: list[str],
    review_expires_at: datetime | None = None,
) -> Application:
    _validate_decision(lane, status, score)
    application = session.exec(
        select(Application).where(Application.opening_id == opening_id)
    ).first()

    if application is not None:
        if application.status == "submitted":
            return application
        application.lane = lane
        application.status = status
        application.score = score
        application.reasons = reasons
        application.red_flags = red_flags
        application.review_expires_at = review_expires_at
        application.updated_at = utcnow()
        if status == "submitted" and application.submitted_at is None:
            application.submitted_at = application.updated_at
    else:
        now = utcnow()
        application = Application(
            opening_id=opening_id,
            lane=lane,
            status=status,
            score=score,
            reasons=reasons,
            red_flags=red_flags,
            review_expires_at=review_expires_at,
            submitted_at=now if status == "submitted" else None,
            created_at=now,
            updated_at=now,
        )
        session.add(application)

    session.flush()
    return application


def transition_application(
    session: Session,
    application: Application,
    *,
    lane: ApplicationLane,
    status: ApplicationStatus,
    event_type: str,
    details: dict | None = None,
) -> Application:
    _validate_decision(lane, status, application.score)
    if (application.status, status) not in _ALLOWED_TRANSITIONS:
        raise ValueError(
            f"invalid application transition from {application.status!r} to {status!r}"
        )
    sanitized_details = _sanitize_event_details(details)

    now = utcnow()
    application.lane = lane
    application.status = status
    application.updated_at = now
    if status == "submitted":
        application.submitted_at = now

    session.add(application)
    record_application_event(
        session,
        application.id,
        event_type=event_type,
        details=sanitized_details,
    )
    return application


def get_application(session: Session, application_id: UUID) -> Application | None:
    return session.get(Application, application_id)


def list_applications(
    session: Session,
    *,
    lane: ApplicationLane | None = None,
    status: ApplicationStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Application]:
    statement = select(Application).order_by(Application.created_at.desc(), Application.id)
    if lane is not None:
        statement = statement.where(Application.lane == lane)
    if status is not None:
        statement = statement.where(Application.status == status)
    return list(session.exec(statement.offset(offset).limit(limit)).all())
