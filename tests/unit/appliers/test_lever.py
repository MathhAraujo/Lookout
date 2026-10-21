"""Lever applier tests: apply-link routing, dry-run fill, and submit recording."""

from pathlib import Path

from _helpers import base_url, lever_answers, make_application, make_opening
from lookout.appliers import ApplicationForm, ApplierError, LeverApplier
from lookout.browser_sessions import (
    BrowserSessionError,
    BrowserSessionInUseError,
    BrowserSessionManager,
)


class _FailingSessions:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.open_calls: list[tuple] = []

    def open(self, platform, *, headless):
        self.open_calls.append((platform, headless))
        raise self.error


def _sessions(tmp_path: Path):
    return BrowserSessionManager(tmp_path / "browser-profiles")


def test_inspect_routes_through_apply_link_and_reads_form(local_site, resume_pdf, tmp_path):
    applier = LeverApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/lever_posting.html", source="lever")

    form = applier.inspect(opening, resume_path=resume_pdf)

    assert isinstance(form, ApplicationForm)
    fields = {field.key: field for field in form.fields}
    assert set(fields) == {
        "name",
        "email",
        "phone",
        "experience_years",
        "authorized_to_work_in_brazil",
    }
    assert fields["name"].required is True
    assert fields["phone"].required is False
    assert fields["authorized_to_work_in_brazil"].options == (
        "Yes, authorized",
        "Requires sponsorship",
    )
    assert local_site.recorder.submission_posts == 0


def test_inspect_on_verification_page_raises_sanitized_error(local_site, resume_pdf, tmp_path):
    applier = LeverApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/lever_verification.html", source="lever")

    try:
        applier.inspect(opening, resume_path=resume_pdf)
    except ApplierError as error:
        assert error.detail == "manual_verification_required"
    else:
        raise AssertionError("inspect must report verification barriers as sanitized errors")


def test_submit_dry_run_routes_and_fills_without_clicking(local_site, resume_pdf, tmp_path):
    applier = LeverApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/lever_posting.html", source="lever")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=resume_pdf,
        answers=lever_answers(),
        dry_run=True,
        auto_submit_enabled=False,
    )

    assert result.status == "dry_run"
    assert result.detail == "dry_run_fill_succeeded"
    assert local_site.recorder.submission_posts == 0


def test_submit_real_click_records_one_submission(local_site, resume_pdf, tmp_path):
    applier = LeverApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/lever_posting.html", source="lever")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=resume_pdf,
        answers=lever_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "submitted"
    assert result.detail == "submission_confirmed"
    assert local_site.recorder.submission_posts == 1


def test_submit_on_verification_page_degrades_to_manual_assist(local_site, resume_pdf, tmp_path):
    applier = LeverApplier(_sessions(tmp_path))
    opening = make_opening(f"{base_url(local_site)}/lever_verification.html", source="lever")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=resume_pdf,
        answers=lever_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "manual_verification_required"
    assert local_site.recorder.submission_posts == 0


def test_submit_locked_profile_degrades_to_manual_assist(local_site, resume_pdf):
    sessions = _FailingSessions(BrowserSessionInUseError("locked"))
    applier = LeverApplier(sessions)
    opening = make_opening("http://127.0.0.1:9/lever_posting.html", source="lever")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=resume_pdf,
        answers=lever_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "browser_profile_in_use"


def test_submit_unavailable_session_degrades_to_manual_assist(local_site, resume_pdf):
    sessions = _FailingSessions(BrowserSessionError("boom"))
    applier = LeverApplier(sessions)
    opening = make_opening("http://127.0.0.1:9/lever_posting.html", source="lever")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=resume_pdf,
        answers=lever_answers(),
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert result.status == "manual_assist"
    assert result.detail == "browser_session_unavailable"
