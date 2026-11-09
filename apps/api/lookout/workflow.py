"""Durable matching, application preparation, and guarded submission."""

import hashlib
import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Session, select

from lookout.applications import transition_application
from lookout.appliers import (
    ApplierError,
    ApplyResult,
    EmailApplier,
    GreenhouseApplier,
    LeverApplier,
)
from lookout.artifacts import ArtifactStore, build_artifact_object_key, build_artifact_store
from lookout.browser_sessions import BrowserSessionManager
from lookout.config import Settings
from lookout.facts import FactsError, load_facts
from lookout.kb import load_identity, load_knowledge_base
from lookout.llm import OpenRouterClient
from lookout.match_profile import load_match_profile
from lookout.matching import build_scoring_client, evaluate_opening, load_matching_policy
from lookout.models import Application, ApplicationAnswer, ApplicationArtifact, Job, Opening
from lookout.queue import enqueue, owned_job
from lookout.routing import approve_review, decline_review, persist_decision
from lookout.screener import ResolvedAnswer, screen_questions
from lookout.secrets import InfisicalSecretProvider
from lookout.tailor.pipeline import tailor_resume


class WorkflowBusyError(Exception):
    """Another worker owns this application's cross-transaction operation."""


class ObsoleteWorkflowAttempt(Exception):
    """The queue lease was reclaimed before submission."""


_SAFE_CONNECTOR_DETAILS = frozenset(
    {
        "unsupported_application_target",
        "browser_profile_in_use",
        "browser_session_unavailable",
        "browser_platform_unavailable",
        "browser_session_expired",
        "manual_verification_required",
        "apply_form_unavailable",
        "unsupported_required_control",
        "required_answers_missing",
        "option_value_missing",
        "resume_artifact_missing",
        "submit_unconfirmed",
        "application_email_missing",
        "smtp_configuration_missing",
        "smtp_password_unavailable",
        "smtp_send_failed",
        "auto_submit_disabled",
        "lane_not_auto_apply",
        "status_not_submitting",
    }
)


def _safe_connector_detail(detail: str) -> str:
    return detail if detail in _SAFE_CONNECTOR_DETAILS else "connector_requires_manual_assistance"


def enqueue_matches(session: Session, opening_ids: Iterable[UUID]) -> int:
    count = 0
    for opening_id in opening_ids:
        opening = session.exec(
            select(Opening).where(Opening.id == opening_id).with_for_update()
        ).first()
        if opening is None:
            continue
        decided = session.exec(
            select(Application.id).where(Application.opening_id == opening_id)
        ).first()
        queued = session.exec(
            select(Job.id).where(
                Job.type == "match",
                Job.status.in_(["pending", "running"]),
                Job.payload["opening_id"].astext == str(opening_id),
            )
        ).first()
        if decided is None and queued is None:
            enqueue(session, "match", {"opening_id": str(opening_id)})
            count += 1
    return count


def enqueue_backfill(session: Session) -> int:
    opening_ids = session.exec(
        select(Opening.id)
        .outerjoin(Application, Application.opening_id == Opening.id)
        .where(Application.id.is_(None))
        .order_by(Opening.id)
    ).all()
    return enqueue_matches(session, opening_ids)


def enqueue_application(session: Session, application_id: UUID) -> Job:
    return enqueue(session, "apply", {"application_id": str(application_id)})


def review_application(session: Session, application_id: UUID, *, approve: bool) -> Application:
    application = (
        approve_review(session, application_id)
        if approve
        else decline_review(session, application_id)
    )
    enqueue_application(session, application_id)
    return application


def match_opening(session: Session, settings: Settings, opening_id: UUID) -> None:
    opening = session.exec(
        select(Opening).where(Opening.id == opening_id).with_for_update()
    ).first()
    if opening is None:
        raise ValueError("opening not found")
    if session.exec(select(Application.id).where(Application.opening_id == opening_id)).first():
        return
    profile = load_match_profile(settings.match_profile_path)
    policy = load_matching_policy(settings.matching_policy_path)
    with build_scoring_client(settings) as llm:
        decision = evaluate_opening(
            opening, profile, policy, llm=llm, pii=load_identity(settings.kb_path)
        )
    if decision.rejected_reason:
        decision.reasons.append(decision.rejected_reason)
    application = persist_decision(session, opening, decision)
    if application.lane != "rejected":
        enqueue_application(session, application.id)


@contextmanager
def _application_lock(session: Session, application_id: UUID) -> Iterator[None]:
    # A dedicated connection keeps this lock through the pre-submit commit.
    key = application_id.int & ((1 << 63) - 1)
    with session.get_bind().connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
        ).scalar_one()
        if not acquired:
            raise WorkflowBusyError("application is already being processed")
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


def _locked_application(session: Session, application_id: UUID) -> Application:
    application = session.exec(
        select(Application)
        .where(Application.id == application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if application is None:
        raise ValueError("application not found")
    return application


def _artifact(session: Session, application_id: UUID, kind: str) -> ApplicationArtifact | None:
    return session.exec(
        select(ApplicationArtifact)
        .where(
            ApplicationArtifact.application_id == application_id,
            ApplicationArtifact.kind == kind,
        )
        .order_by(ApplicationArtifact.created_at.desc(), ApplicationArtifact.id)
    ).first()


def _save_artifact(
    session: Session,
    store: ArtifactStore,
    application: Application,
    *,
    path: Path,
    kind: str,
    content_type: str,
) -> None:
    artifact_id = uuid4()
    key = build_artifact_object_key(application.id, artifact_id, kind)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    store.put_file(key=key, path=path, content_type=content_type)
    session.add(
        ApplicationArtifact(
            id=artifact_id,
            application_id=application.id,
            kind=kind,
            object_key=key,
            content_type=content_type,
            sha256=digest,
        )
    )
    session.flush()


def _save_json(session, store, application, directory, kind, value):
    path = directory / f"{kind}.json"
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    existing = _artifact(session, application.id, kind)
    if existing is not None and existing.sha256 == hashlib.sha256(path.read_bytes()).hexdigest():
        return
    _save_artifact(
        session, store, application, path=path, kind=kind, content_type="application/json"
    )


def _save_record(session, store, application, directory):
    _save_json(
        session,
        store,
        application,
        directory,
        "opening_record",
        {
            "application_id": str(application.id),
            "opening_id": str(application.opening_id),
            "lane": application.lane,
            "status": application.status,
            "score": application.score,
            "dry_run": application.dry_run,
            "last_error": application.last_error,
        },
    )


def _prepare_resume(session, settings, application, store, directory) -> Path:
    existing = _artifact(session, application.id, "resume")
    if existing is not None:
        data = store.get_bytes(existing.object_key)
        if hashlib.sha256(data).hexdigest() != existing.sha256:
            raise ValueError("resume artifact integrity check failed")
        path = directory / "resume.pdf"
        path.write_bytes(data)
        return path
    with OpenRouterClient(
        api_key=settings.openrouter_api_key, model=settings.openrouter_tailoring_model
    ) as llm:
        path = tailor_resume(
            session,
            opening_id=application.opening_id,
            kb_path=settings.kb_path,
            out_dir=directory,
            llm=llm,
        )
    _save_artifact(
        session, store, application, path=path, kind="resume", content_type="application/pdf"
    )
    return path


def build_applier(opening: Opening, settings: Settings):
    sessions = BrowserSessionManager(settings.browser_profiles_path)
    if opening.source == "greenhouse":
        return GreenhouseApplier(sessions)
    if opening.source == "lever":
        return LeverApplier(sessions)
    if opening.source != "linkedin_email" and opening.application_email:
        return EmailApplier(settings, InfisicalSecretProvider(settings))
    raise ApplierError("unsupported_application_target")


def _screen(session, application, questions, settings, llm):
    kb = load_knowledge_base(settings.kb_path)
    facts = load_facts(settings.facts_path)
    parts = kb.identity.full_name.split(maxsplit=1)
    identity = {
        "name": kb.identity.full_name,
        "full_name": kb.identity.full_name,
        "first_name": parts[0] if parts else "",
        "last_name": parts[1] if len(parts) > 1 else "",
        "email": kb.identity.email,
        "phone": kb.identity.phone,
    }
    local, remaining = [], []
    for question in questions:
        if question.key not in identity:
            remaining.append(question)
            continue
        value = identity[question.key]
        if question.options:
            value = next(
                (option for option in question.options if option.casefold() == value.casefold()), ""
            )
        status = "answered" if value else "blocked" if question.required else "skipped"
        local.append(ResolvedAnswer(question.key, value or None, "fact", status))
    session.add_all(
        ApplicationAnswer(
            application_id=application.id,
            question_key=answer.key,
            source=answer.source,
            status=answer.status,
        )
        for answer in local
    )
    return local + screen_questions(
        session, application, remaining, facts=facts, kb=kb, llm=llm, pii=kb.identity
    )


def _manual(session, application, detail, *, blocked=False):
    application.last_error = detail
    transition_application(
        session,
        application,
        lane="manual_assist",
        status="blocked" if blocked else "manual_assist",
        event_type="application_blocked" if blocked else "manual_assist",
    )


def _assert_lease(session, lease):
    if lease is not None and owned_job(session, *lease) is None:
        raise ObsoleteWorkflowAttempt("worker lease is no longer owned")


def apply_application(
    session: Session,
    settings: Settings,
    application_id: UUID,
    *,
    lease: tuple[UUID, int] | None = None,
) -> None:
    with _application_lock(session, application_id):
        application = _locked_application(session, application_id)
        if application.status == "submitting":
            _manual(session, application, "submission_outcome_unknown")
            session.commit()
        if application.status == "rejected":
            return
        terminal = application.status in {"submitted", "blocked", "dry_run", "expired"}
        prepared_manual = (
            application.status == "manual_assist"
            and _artifact(session, application.id, "resume") is not None
        )
        if terminal or prepared_manual:
            if _artifact(session, application.id, "resume") is not None:
                with TemporaryDirectory(prefix="lookout-application-") as temporary:
                    _save_record(
                        session, build_artifact_store(settings), application, Path(temporary)
                    )
            return
        opening = session.get(Opening, application.opening_id)
        store = build_artifact_store(settings)
        with TemporaryDirectory(prefix="lookout-application-") as temporary:
            directory = Path(temporary)
            resume_path = _prepare_resume(session, settings, application, store, directory)
            application.last_error = None
            if application.lane in {"review", "manual_assist"}:
                _save_record(session, store, application, directory)
                return
            if application.lane != "auto_apply" or application.status != "ready":
                return
            try:
                applier = build_applier(opening, settings)
                form = applier.inspect(opening, resume_path=resume_path)
            except ApplierError as error:
                _manual(session, application, _safe_connector_detail(error.detail))
                _save_record(session, store, application, directory)
                return
            try:
                with OpenRouterClient(
                    api_key=settings.openrouter_api_key, model=settings.openrouter_tailoring_model
                ) as llm:
                    answers = _screen(session, application, form.fields, settings, llm)
            except FactsError:
                _manual(session, application, "approved_facts_unavailable", blocked=True)
                _save_record(session, store, application, directory)
                return
            _save_json(
                session,
                store,
                application,
                directory,
                "answers",
                [asdict(answer) for answer in answers],
            )
            if any(answer.status == "blocked" for answer in answers):
                _manual(session, application, "required_answers_missing", blocked=True)
                _save_record(session, store, application, directory)
                return
            _assert_lease(session, lease)
            dry_run = settings.dry_run or not settings.auto_submit_enabled
            application.dry_run = dry_run
            if not dry_run:
                transition_application(
                    session,
                    application,
                    lane="auto_apply",
                    status="submitting",
                    event_type="submission_started",
                )
                session.commit()
                _assert_lease(session, lease)
                session.commit()
            try:
                result = applier.submit(
                    application,
                    opening,
                    resume_path=resume_path,
                    answers=answers,
                    dry_run=dry_run,
                    auto_submit_enabled=settings.auto_submit_enabled,
                )
            except Exception:  # noqa: BLE001 - never retry a possibly completed submission
                result = ApplyResult("manual_assist", "submit_unconfirmed")
            application = _locked_application(session, application_id)
            if result.status == "manual_assist":
                _manual(session, application, _safe_connector_detail(result.detail))
            else:
                expected = "dry_run" if dry_run else "submitted"
                if result.status != expected:
                    _manual(session, application, "unexpected_connector_result")
                else:
                    transition_application(
                        session,
                        application,
                        lane="auto_apply",
                        status=expected,
                        event_type="application_" + expected,
                    )
            session.commit()
            _save_record(session, store, application, directory)
