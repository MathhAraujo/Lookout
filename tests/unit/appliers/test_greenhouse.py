"""Greenhouse applier tests against a local fictional application form."""

from pathlib import Path

from _helpers import base_url, greenhouse_answers, make_application, make_opening
from lookout.appliers import ApplicationForm, ApplierError, ApplyResult, GreenhouseApplier
from lookout.browser_sessions import BrowserSessionError, BrowserSessionInUseError
from lookout.screener import FormQuestion


class _FailingSessions:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.open_calls: list[tuple] = []

    def open(self, platform, *, headless):
        self.open_calls.append((platform, headless))
        raise self.error


def _sessions(tmp_path: Path):
    from lookout.browser_sessions import BrowserSessionManager

    return BrowserSessionManager(tmp_path / "browser-profiles")


def test_inspect_reads_supported_application_fields(local_site, resume_pdf, tmp_path):
    applier = GreenhouseApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/greenhouse_form.html")

    form = applier.inspect(opening, resume_path=resume_pdf)

    assert isinstance(form, ApplicationForm)
    fields = {field.key: field for field in form.fields}
    assert set(fields) == {
        "first_name",
        "last_name",
        "email",
        "phone",
        "years_of_python_experience",
        "are_you_authorized_to_work_in_brazil",
    }
    assert fields["first_name"].required is True
    assert fields["phone"].required is False
    assert fields["are_you_authorized_to_work_in_brazil"].options == (
        "Yes, authorized",
        "Requires sponsorship",
    )
    assert all(isinstance(field, FormQuestion) for field in form.fields)


def test_inspect_missing_form_raises_sanitized_error(local_site, resume_pdf, tmp_path):
    applier = GreenhouseApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/not_there.html")

    try:
        applier.inspect(opening, resume_path=resume_pdf)
    except ApplierError as error:
        assert error.detail == "browser_platform_unavailable"
    else:
        raise AssertionError("inspect must report a missing form page as a sanitized error")


def test_submit_dry_run_fills_without_clicking_submit(local_site, resume_pdf, tmp_path):
    applier = GreenhouseApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/greenhouse_form.html")
    application = make_application()

    result = applier.submit(
        application,
        opening,
        resume_path=resume_pdf,
        answers=greenhouse_answers(),
        dry_run=True,
        auto_submit_enabled=False,
    )

    assert result.status == "dry_run"
    assert result.detail == "dry_run_fill_succeeded"
    assert local_site.recorder.submission_posts == 0


def test_submit_real_click_records_one_submission(local_site, resume_pdf, tmp_path):
    applier = GreenhouseApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/greenhouse_form.html")
    application = make_application()

    result = applier.submit(
        application,
        opening,
        resume_path=resume_pdf,
        answers=greenhouse_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "submitted"
    assert result.detail == "submission_confirmed"
    assert local_site.recorder.submission_posts == 1


def test_submit_without_confirmation_degrades_to_manual_assist(local_site, resume_pdf, tmp_path):
    applier = GreenhouseApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/greenhouse_no_confirm.html")
    application = make_application()

    result = applier.submit(
        application,
        opening,
        resume_path=resume_pdf,
        answers=greenhouse_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "submit_unconfirmed"
    # A single POST happened and no retry may fire.
    assert local_site.recorder.submission_posts == 1


def test_submit_detects_captcha_barrier(local_site, resume_pdf, tmp_path):
    applier = GreenhouseApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/greenhouse_captcha.html")
    application = make_application()

    result = applier.submit(
        application,
        opening,
        resume_path=resume_pdf,
        answers=greenhouse_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "manual_verification_required"
    assert local_site.recorder.submission_posts == 0


def test_submit_detects_expired_session(local_site, resume_pdf, tmp_path):
    applier = GreenhouseApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/greenhouse_session_expired.html")
    application = make_application()

    result = applier.submit(
        application,
        opening,
        resume_path=resume_pdf,
        answers=greenhouse_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "browser_session_expired"
    assert local_site.recorder.submission_posts == 0


def test_submit_guard_blocks_real_submission(local_site, resume_pdf, tmp_path):
    applier = GreenhouseApplier(_FailingSessions(BrowserSessionError("no session expected")))
    opening = make_opening(f"{base_url(local_site)}/greenhouse_form.html")
    answers = greenhouse_answers()

    flags_off = applier.submit(
        make_application(),
        opening,
        resume_path=resume_pdf,
        answers=answers,
        dry_run=False,
        auto_submit_enabled=False,
    )
    review_lane = applier.submit(
        make_application(lane="review"),
        opening,
        resume_path=resume_pdf,
        answers=answers,
        dry_run=False,
        auto_submit_enabled=True,
    )
    not_submitting = applier.submit(
        make_application(status="ready"),
        opening,
        resume_path=resume_pdf,
        answers=answers,
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert (flags_off.status, flags_off.detail) == ("manual_assist", "auto_submit_disabled")
    assert (review_lane.status, review_lane.detail) == ("manual_assist", "lane_not_auto_apply")
    assert (not_submitting.status, not_submitting.detail) == (
        "manual_assist",
        "status_not_submitting",
    )
    assert isinstance(flags_off, ApplyResult)
    assert local_site.recorder.submission_posts == 0
    assert applier._sessions.open_calls == []


def test_submit_locked_profile_degrades_to_manual_assist(local_site, resume_pdf, tmp_path):
    sessions = _FailingSessions(BrowserSessionInUseError("locked"))
    applier = GreenhouseApplier(sessions)
    opening = make_opening(f"{base_url(local_site)}/greenhouse_form.html")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=resume_pdf,
        answers=greenhouse_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "browser_profile_in_use"
    assert local_site.recorder.submission_posts == 0


def test_submit_unavailable_session_degrades_to_manual_assist(local_site, resume_pdf, tmp_path):
    sessions = _FailingSessions(BrowserSessionError("boom"))
    applier = GreenhouseApplier(sessions)
    opening = make_opening(f"{base_url(local_site)}/greenhouse_form.html")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=resume_pdf,
        answers=greenhouse_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "browser_session_unavailable"
    assert local_site.recorder.submission_posts == 0


def test_submit_missing_resume_never_opens_a_browser(local_site, tmp_path):
    sessions = _FailingSessions(BrowserSessionError("no session expected"))
    applier = GreenhouseApplier(sessions)
    opening = make_opening(f"{base_url(local_site)}/greenhouse_form.html")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=tmp_path / "absent-resume.pdf",
        answers=greenhouse_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "resume_artifact_missing"
    assert local_site.recorder.submission_posts == 0
    assert sessions.open_calls == []


def test_dry_run_with_missing_resume_still_refuses(local_site, tmp_path):
    applier = GreenhouseApplier(_FailingSessions(BrowserSessionError("no session expected")))
    opening = make_opening(f"{base_url(local_site)}/greenhouse_form.html")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=tmp_path / "absent-resume.pdf",
        answers=greenhouse_answers(),
        dry_run=True,
        auto_submit_enabled=False,
    )

    assert result.status == "manual_assist"
    assert result.detail == "resume_artifact_missing"
