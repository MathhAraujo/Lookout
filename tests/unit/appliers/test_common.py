"""Shared applier contracts: ApplyResult shape and the submission guard."""

from _helpers import make_application
from lookout.appliers import ApplicationForm, ApplyResult
from lookout.appliers.base import submission_guard
from lookout.screener import FormQuestion, ResolvedAnswer


def test_apply_result_carries_status_and_sanitized_detail():
    result = ApplyResult("dry_run", "dry_run_fill_succeeded")

    assert result.status == "dry_run"
    assert result.detail == "dry_run_fill_succeeded"


def test_application_form_holds_screenable_questions():
    question = FormQuestion(key="first_name", label="First name", required=True)
    form = ApplicationForm(fields=[question])

    assert form.fields == [question]


def test_dry_run_takes_no_guard():
    guard = submission_guard(make_application(), dry_run=True, auto_submit_enabled=False)

    assert guard is None


def test_guard_requires_auto_submit_enabled():
    guard = submission_guard(make_application(), dry_run=False, auto_submit_enabled=False)

    assert (guard.status, guard.detail) == ("manual_assist", "auto_submit_disabled")


def test_guard_requires_auto_apply_lane():
    guard = submission_guard(
        make_application(lane="review"), dry_run=False, auto_submit_enabled=True
    )

    assert (guard.status, guard.detail) == ("manual_assist", "lane_not_auto_apply")


def test_guard_requires_submitting_status():
    guard = submission_guard(
        make_application(status="ready"), dry_run=False, auto_submit_enabled=True
    )

    assert (guard.status, guard.detail) == ("manual_assist", "status_not_submitting")


def test_guard_allows_a_compliant_real_submission():
    assert submission_guard(make_application(), dry_run=False, auto_submit_enabled=True) is None


def test_resolved_answer_shape_is_shared_with_screener():
    answer = ResolvedAnswer(key="first_name", answer="Ada", source="fact", status="answered")

    assert answer.key == "first_name"
    assert answer.status == "answered"
