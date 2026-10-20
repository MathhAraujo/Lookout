import json
from pathlib import Path

import pytest
from lookout.kb import load_knowledge_base
from lookout.tailor.schema import TailoredExperience, TailoredProject, TailoredResume
from lookout.tailor.validation import validate_resume


@pytest.fixture
def kb():
    return load_knowledge_base(Path("tests/fixtures/kb"))


def load_resume(name: str) -> TailoredResume:
    path = Path("tests/fixtures/tailor") / name
    return TailoredResume.model_validate(json.loads(path.read_text()))


def valid_fixture_resume() -> TailoredResume:
    return load_resume("llm_response_en.json")


def test_validation_flags_fabricated_facts(kb):
    violations = validate_resume(load_resume("llm_response_invalid.json"), kb)

    assert any("exp-ghost" in violation for violation in violations)
    assert any("Kubernetes" in violation for violation in violations)


def test_validation_accepts_kb_only_resume(kb):
    assert validate_resume(valid_fixture_resume(), kb) == []


def test_validation_rejects_claims_not_present_in_knowledge_base(kb):
    resume = TailoredResume(
        language="en",
        summary="Managed a team of 20 engineers.",
        experiences=[
            TailoredExperience(
                kb_id="exp-acme",
                highlights=["Led a team of 20 engineers."],
            )
        ],
        projects=[
            TailoredProject(
                kb_id="proj-lookout",
                highlights=["Increased revenue by 300% with the platform."],
            )
        ],
        skills=["Python"],
    )

    violations = validate_resume(resume, kb)

    assert any("summary" in violation.lower() for violation in violations)
    assert any("experience highlight" in violation.lower() for violation in violations)
    assert any("project highlight" in violation.lower() for violation in violations)
