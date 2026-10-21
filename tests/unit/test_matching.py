import json
from pathlib import Path

import pytest
from lookout.config import Settings
from lookout.llm import LLMError
from lookout.match_profile import (
    MatchProfile,
    MatchProfileError,
    load_match_profile,
)
from lookout.matching import (
    FilterResult,
    MatchDecision,
    MatchingConfigurationError,
    MatchingPolicy,
    MatchingPolicyError,
    SalaryRange,
    build_scoring_client,
    deterministic_filter,
    evaluate_opening,
    extract_salary,
    load_matching_policy,
)
from lookout.models import Opening
from lookout.redaction import PiiProfile, contains_pii
from pydantic import ValidationError

PII = PiiProfile(
    full_name="Candidate Example",
    cpf="123.456.789-09",
    phone="+55 11 91234-5678",
    address="42 Fictional Street, Example City",
    email="candidate@example.com",
)


def make_profile(**overrides) -> MatchProfile:
    values = {
        "ideal_job": "Senior Python backend engineer",
        "include_keywords": ["python"],
        "exclude_keywords": [],
        "allowed_languages": [],
        "allowed_locations": [],
        "allowed_work_modes": [],
        "minimum_seniority": None,
        "minimum_salary": None,
        "salary_currency": None,
    }
    values.update(overrides)
    return MatchProfile(**values)


def make_opening(
    *,
    source: str = "greenhouse",
    title: str = "Senior Python Engineer",
    location: str | None = "Remote",
    description: str = "We are looking for a Python engineer.",
    raw: dict | None = None,
    application_email: str | None = None,
) -> Opening:
    return Opening(
        source=source,
        external_id="fictional-opening-1",
        company="Globex Corporation",
        title=title,
        location=location,
        url="https://example.com/jobs/fictional-opening-1",
        description=description,
        dedup_key="globex|senior python engineer",
        raw=raw or {},
        application_email=application_email,
    )


class FakeScoringLLM:
    def __init__(self, response=None, error: Exception | None = None):
        response_path = Path("tests/fixtures/matching/scoring-response.json")
        self.response = (
            response
            if response is not None
            else json.loads(response_path.read_text(encoding="utf-8"))
        )
        self.error = error
        self.calls = 0
        self.last_system = ""
        self.last_user = ""

    def complete_json(self, *, system: str, user: str) -> dict:
        self.calls += 1
        self.last_system = system
        self.last_user = user
        if self.error is not None:
            raise self.error
        return self.response


def test_load_match_profile_reads_fictional_profile_fields(tmp_path):
    path = tmp_path / "match-profile.yml"
    path.write_text(
        """
ideal_job: Senior Python backend engineer
include_keywords: [python, fastapi]
exclude_keywords: [commission-only]
allowed_languages: [English, Portuguese]
allowed_locations: [Brazil, Worldwide]
allowed_work_modes: [remote, hybrid]
minimum_seniority: senior
minimum_salary: 90000
salary_currency: USD
""",
        encoding="utf-8",
    )

    profile = load_match_profile(path)

    assert profile.ideal_job == "Senior Python backend engineer"
    assert profile.include_keywords == ["python", "fastapi"]
    assert profile.minimum_seniority == "senior"
    assert profile.minimum_salary == 90000
    assert profile.salary_currency == "USD"


def test_load_match_profile_rejects_unknown_seniority(tmp_path):
    path = tmp_path / "match-profile.yml"
    path.write_text("ideal_job: Engineer\nminimum_seniority: lead\n", encoding="utf-8")

    with pytest.raises(MatchProfileError, match="invalid match profile"):
        load_match_profile(path)


def test_match_profile_rejects_unrecognized_seniority():
    with pytest.raises(ValidationError):
        make_profile(minimum_seniority="lead")


def test_matching_policy_defaults_and_loads_configured_score_bands():
    policy = load_matching_policy(Path("config/matching.yml"))

    assert policy == MatchingPolicy(auto_apply_min_score=90, review_min_score=70)


@pytest.mark.parametrize(
    ("review_min_score", "auto_apply_min_score"),
    [(70, 70), (80, 70), (-1, 90), (70, 101)],
)
def test_matching_policy_rejects_invalid_score_band_order(review_min_score, auto_apply_min_score):
    with pytest.raises(ValidationError):
        MatchingPolicy(
            review_min_score=review_min_score,
            auto_apply_min_score=auto_apply_min_score,
        )


def test_load_matching_policy_reports_invalid_configuration(tmp_path):
    path = tmp_path / "matching.yml"
    path.write_text("review_min_score: 91\nauto_apply_min_score: 90\n", encoding="utf-8")

    with pytest.raises(MatchingPolicyError, match="invalid matching policy"):
        load_matching_policy(path)


def test_deterministic_filter_rejects_excluded_keyword_case_insensitively():
    result = deterministic_filter(
        make_opening(description="Python engineer for a commission-only role."),
        make_profile(exclude_keywords=["COMMISSION-ONLY"]),
    )

    assert result == FilterResult(eligible=False, reason="excluded_keyword")


def test_deterministic_filter_requires_any_configured_include_keyword():
    result = deterministic_filter(
        make_opening(title="Database Administrator", description="Oracle operations."),
        make_profile(include_keywords=["python", "fastapi"]),
    )

    assert result == FilterResult(eligible=False, reason="no_include_keyword_match")


def test_empty_include_keywords_disable_include_filter():
    result = deterministic_filter(
        make_opening(title="Database Administrator", description="Oracle operations."),
        make_profile(include_keywords=[]),
    )

    assert result.eligible
    assert result.reason is None


@pytest.mark.parametrize(
    ("title", "minimum_seniority", "eligible"),
    [
        ("Intern Python Engineer", "junior", False),
        ("Junior Python Engineer", "senior", False),
        ("Mid-level Python Engineer", "senior", False),
        ("Senior Python Engineer", "senior", True),
        ("Principal Python Engineer", "staff", True),
        ("Python Engineer", "senior", True),
    ],
)
def test_seniority_filter_orders_recognized_levels_and_keeps_unknown_levels(
    title, minimum_seniority, eligible
):
    result = deterministic_filter(
        make_opening(title=title),
        make_profile(minimum_seniority=minimum_seniority),
    )

    assert result.eligible is eligible
    if not eligible:
        assert result.reason == "seniority_below_minimum"


def test_deterministic_filter_rejects_explicit_location_conflict():
    result = deterministic_filter(
        make_opening(location="Austin, Texas, United States"),
        make_profile(allowed_locations=["Brazil"]),
    )

    assert result == FilterResult(eligible=False, reason="location_not_allowed")


@pytest.mark.parametrize("location", ["Remote", "Worldwide remote"])
def test_generic_remote_location_is_not_a_geo_conflict(location):
    result = deterministic_filter(
        make_opening(location=location),
        make_profile(allowed_locations=["Brazil"]),
    )

    assert result.eligible


def test_deterministic_filter_rejects_explicit_language_conflict():
    result = deterministic_filter(
        make_opening(raw={"language": "pt-BR"}),
        make_profile(allowed_languages=["English"]),
    )

    assert result == FilterResult(eligible=False, reason="language_not_allowed")


def test_unclassified_posting_language_does_not_reject():
    result = deterministic_filter(
        make_opening(title="Ingénieur Python", description="Construire des outils internes."),
        make_profile(allowed_languages=["Portuguese"]),
    )

    assert result.eligible


def test_deterministic_filter_rejects_explicit_work_mode_conflict():
    result = deterministic_filter(
        make_opening(raw={"work_mode": "on-site"}),
        make_profile(allowed_work_modes=["remote"]),
    )

    assert result == FilterResult(eligible=False, reason="work_mode_not_allowed")


def test_hybrid_remote_posting_matches_hybrid_work_mode():
    result = deterministic_filter(
        make_opening(raw={"work_mode": "hybrid remote"}),
        make_profile(allowed_work_modes=["hybrid"]),
    )

    assert result.eligible


def test_unknown_work_mode_does_not_reject():
    result = deterministic_filter(
        make_opening(raw={"workMode": "flexible schedule"}),
        make_profile(allowed_work_modes=["remote"]),
    )

    assert result.eligible


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            {"salary_min": 90000, "salary_max": 120000, "salary_currency": "USD"},
            SalaryRange(minimum=90000, maximum=120000, currency="USD"),
        ),
        (
            {"salaryMin": "85000", "salaryMax": "110000", "salaryCurrency": "BRL"},
            SalaryRange(minimum=85000, maximum=110000, currency="BRL"),
        ),
        ({"salary": "$90,000 per year"}, None),
        ({}, None),
    ],
)
def test_extract_salary_reads_only_supported_structured_keys(raw, expected):
    assert extract_salary(raw) == expected


def test_matching_salary_below_minimum_rejects_when_currency_matches():
    result = deterministic_filter(
        make_opening(
            raw={
                "salary_min": 50000,
                "salary_max": 80000,
                "salary_currency": "USD",
            }
        ),
        make_profile(minimum_salary=90000, salary_currency="USD"),
    )

    assert result == FilterResult(eligible=False, reason="salary_below_minimum")


def test_missing_salary_does_not_reject():
    result = deterministic_filter(
        make_opening(raw={}),
        make_profile(minimum_salary=90000, salary_currency="USD"),
    )

    assert result.eligible


def test_salary_currency_mismatch_does_not_reject():
    result = deterministic_filter(
        make_opening(raw={"salary_min": 50000, "salary_max": 70000, "salary_currency": "BRL"}),
        make_profile(minimum_salary=90000, salary_currency="USD"),
    )

    assert result.eligible


def test_salary_range_that_reaches_minimum_does_not_reject():
    result = deterministic_filter(
        make_opening(raw={"salary_min": 80000, "salary_max": 100000, "salary_currency": "USD"}),
        make_profile(minimum_salary=90000, salary_currency="USD"),
    )

    assert result.eligible


def test_deterministic_rejection_does_not_call_the_llm():
    llm = FakeScoringLLM()

    decision = evaluate_opening(
        make_opening(
            title="Oracle Database Administrator",
            description="Administration of Oracle databases.",
        ),
        make_profile(include_keywords=["python"]),
        MatchingPolicy(),
        llm=llm,
        pii=PII,
    )

    assert decision.lane == "rejected"
    assert decision.score is None
    assert decision.rejected_reason == "no_include_keyword_match"
    assert llm.calls == 0


@pytest.mark.parametrize(
    ("source", "score", "application_email", "expected_lane"),
    [
        ("greenhouse", 90, None, "auto_apply"),
        ("lever", 89, None, "review"),
        ("remoteok", 99, None, "manual_assist"),
        ("remoteok", 90, "apply@example.com", "auto_apply"),
        ("remoteok", 75, "apply@example.com", "review"),
        ("greenhouse", 69, None, "rejected"),
    ],
)
def test_score_bands_route_openings_by_target(source, score, application_email, expected_lane):
    llm = FakeScoringLLM({"score": score, "reasons": ["Relevant skills"], "red_flags": []})

    decision = evaluate_opening(
        make_opening(source=source, application_email=application_email),
        make_profile(),
        MatchingPolicy(),
        llm=llm,
        pii=PII,
    )

    assert decision.lane == expected_lane
    assert decision.score == score


def test_linkedin_alert_stays_manual_assist_even_with_application_email():
    decision = evaluate_opening(
        make_opening(
            source="linkedin_email",
            application_email="apply@example.com",
        ),
        make_profile(),
        MatchingPolicy(),
        llm=FakeScoringLLM(),
        pii=PII,
    )

    assert decision.lane == "manual_assist"


@pytest.mark.parametrize(
    "response",
    [
        {"score": 101, "reasons": ["Valid"], "red_flags": []},
        {"score": -1, "reasons": ["Valid"], "red_flags": []},
        {"score": True, "reasons": ["Invalid boolean"], "red_flags": []},
        {"score": 90, "reasons": "not a list", "red_flags": []},
        {"score": 90, "red_flags": []},
    ],
)
def test_invalid_scoring_output_fails_closed_to_manual_assist(response):
    decision = evaluate_opening(
        make_opening(),
        make_profile(),
        MatchingPolicy(),
        llm=FakeScoringLLM(response),
        pii=PII,
    )

    assert decision == MatchDecision(
        score=None,
        reasons=[],
        red_flags=["invalid_scoring_response"],
        lane="manual_assist",
        rejected_reason=None,
    )


def test_invalid_json_from_openrouter_fails_closed_without_error_details():
    llm = FakeScoringLLM(error=LLMError(f"invalid JSON containing {PII.full_name}"))

    decision = evaluate_opening(
        make_opening(),
        make_profile(),
        MatchingPolicy(),
        llm=llm,
        pii=PII,
    )

    assert decision.lane == "manual_assist"
    assert decision.score is None
    assert decision.red_flags == ["scoring_unavailable"]
    assert PII.full_name not in str(decision)


def test_complete_scoring_prompt_redacts_profile_and_posting_pii():
    llm = FakeScoringLLM()
    profile = make_profile(ideal_job=f"Engineer for {PII.full_name}")
    opening = make_opening(
        description=(
            f"{PII.full_name}, {PII.cpf}, {PII.phone}, {PII.address}, {PII.email}. "
            "We are looking for a Python engineer."
        )
    )

    decision = evaluate_opening(opening, profile, MatchingPolicy(), llm=llm, pii=PII)
    prompt = llm.last_system + llm.last_user

    assert decision.lane == "auto_apply"
    assert llm.calls == 1
    assert not contains_pii(prompt, PII)
    assert "Globex Corporation" in prompt


def test_pii_in_scoring_response_fails_closed_without_returning_it():
    llm = FakeScoringLLM({"score": 99, "reasons": [PII.full_name], "red_flags": []})

    decision = evaluate_opening(
        make_opening(),
        make_profile(),
        MatchingPolicy(),
        llm=llm,
        pii=PII,
    )

    assert decision.lane == "manual_assist"
    assert decision.score is None
    assert decision.reasons == []
    assert PII.full_name not in str(decision)


def test_pii_remaining_after_redaction_skips_llm(monkeypatch):
    from lookout import matching

    monkeypatch.setattr(matching, "redact", lambda text, pii: text)
    llm = FakeScoringLLM()
    opening = make_opening(description=f"{PII.full_name} is a Python engineer.")

    decision = evaluate_opening(
        opening,
        make_profile(),
        MatchingPolicy(),
        llm=llm,
        pii=PII,
    )

    assert decision.lane == "manual_assist"
    assert decision.red_flags == ["unsafe_scoring_payload"]
    assert llm.calls == 0


def test_scoring_client_fails_explicitly_without_model_setting():
    settings = Settings(_env_file=None, openrouter_api_key="fictional-openrouter-key")

    with pytest.raises(MatchingConfigurationError, match="OPENROUTER_SCORING_MODEL"):
        build_scoring_client(settings)


def test_scoring_client_uses_configured_model_without_hardcoding():
    settings = Settings(
        _env_file=None,
        openrouter_api_key="fictional-openrouter-key",
        openrouter_scoring_model="fictional-provider/fictional-model",
    )

    client = build_scoring_client(settings)

    assert client.model == "fictional-provider/fictional-model"
