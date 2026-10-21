from dataclasses import replace
from pathlib import Path

import pytest
from lookout.applications import upsert_application
from lookout.facts import ApprovedFacts, FactsError, load_facts
from lookout.models import ApplicationAnswer
from lookout.redaction import contains_pii
from lookout.screener import (
    FormQuestion,
    ResolvedAnswer,
    classify_question,
    resolve_question,
    screen_questions,
)
from sqlmodel import select

FACTS_PATH = Path("tests/fixtures/facts/facts.yml")


class FakeAnswerLLM:
    def __init__(self, response=None):
        self.response = response or {"answer": "I have built Python services for internal users."}
        self.calls = 0
        self.last_system = ""
        self.last_user = ""

    def complete_json(self, *, system: str, user: str) -> dict:
        self.calls += 1
        self.last_system = system
        self.last_user = user
        return self.response


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Are you legally authorized to work?", "work_authorization"),
        ("Will you require visa sponsorship?", "sponsorship"),
        ("What are your salary expectations?", "salary"),
        ("When can you start?", "start_date"),
        ("Are you willing to relocate?", "relocation"),
        ("Where are you located?", "location"),
        ("How many years of Python experience?", "experience_years"),
        ("Why are you interested in this role?", "motivation"),
        ("Describe your relevant experience", "relevant_experience"),
    ],
)
def test_classify_question_uses_deterministic_label_aliases(label, expected):
    question = FormQuestion(key="question-1", label=label, required=True)

    assert classify_question(question) == expected


def test_unknown_question_label_is_not_classified():
    question = FormQuestion(
        key="question-unknown",
        label="Tell us anything else you would like to share.",
        required=False,
    )

    assert classify_question(question) is None


def test_question_classification_is_case_insensitive():
    question = FormQuestion(
        key="salary",
        label="WHAT ARE YOUR SALARY EXPECTATIONS?",
        required=True,
    )

    assert classify_question(question) == "salary"


def test_load_facts_reads_explicit_values_and_allowed_options():
    facts = load_facts(FACTS_PATH)

    assert facts.facts["work_authorization"].key == "work_authorization"
    assert facts.facts["work_authorization"].value == "Yes"
    assert facts.facts["work_authorization"].allowed_values == ("Yes", "No")


def test_load_facts_rejects_missing_and_malformed_required_files(tmp_path):
    with pytest.raises(FactsError, match="unable to load approved facts"):
        load_facts(tmp_path / "missing.yml")

    malformed = tmp_path / "malformed.yml"
    malformed.write_text("facts: invalid", encoding="utf-8")
    with pytest.raises(FactsError, match="invalid approved facts"):
        load_facts(malformed)


def test_load_facts_rejects_a_value_outside_its_allowed_values(tmp_path):
    path = tmp_path / "facts.yml"
    path.write_text(
        "facts:\n  - key: work_authorization\n    value: Maybe\n    allowed_values: [Yes, No]\n",
        encoding="utf-8",
    )

    with pytest.raises(FactsError, match="invalid approved facts"):
        load_facts(path)


@pytest.mark.parametrize(
    ("key", "label", "value", "options"),
    [
        ("work_authorization", "Are you legally authorized to work?", "Yes", ("Yes", "No")),
        ("sponsorship", "Will you require visa sponsorship?", "No", ("Yes", "No")),
        ("salary", "What are your salary expectations?", "90000 USD", ()),
        ("start_date", "When can you start?", "Two weeks", ()),
        ("relocation", "Are you willing to relocate?", "No", ("Yes", "No")),
        ("location", "Where are you located?", "Sao Paulo, Brazil", ()),
        ("experience_years", "How many years of Python experience?", "5", ()),
    ],
)
def test_factual_questions_use_exact_approved_facts(key, label, value, options, kb):
    llm = FakeAnswerLLM()
    answer = resolve_question(
        FormQuestion(key="application-question-1", label=label, required=True, options=options),
        load_facts(FACTS_PATH),
        kb,
        llm=llm,
        pii=kb.identity,
    )

    assert answer == ResolvedAnswer(
        key="application-question-1",
        answer=value,
        source="fact",
        status="answered",
    )
    assert llm.calls == 0


def test_fact_answer_must_match_form_allowed_values(kb):
    question = FormQuestion(
        key="authorization",
        label="Are you legally authorized to work?",
        required=True,
        options=("No",),
    )

    answer = resolve_question(
        question,
        load_facts(FACTS_PATH),
        kb,
        llm=FakeAnswerLLM(),
        pii=kb.identity,
    )

    assert answer.answer is None
    assert answer.source == "unresolved"
    assert answer.status == "blocked"


def test_disqualifying_question_requires_an_exact_fact_and_never_uses_llm(kb):
    llm = FakeAnswerLLM()
    question = FormQuestion(
        key="sponsorship",
        label="Will you require visa sponsorship?",
        required=False,
        disqualifying=True,
    )

    answer = resolve_question(question, ApprovedFacts(facts={}), kb, llm=llm, pii=kb.identity)

    assert answer.status == "blocked"
    assert answer.answer is None
    assert llm.calls == 0


def test_disqualifying_question_uses_exact_approved_fact_without_inference(kb):
    llm = FakeAnswerLLM()
    question = FormQuestion(
        key="sponsorship",
        label="Will you require visa sponsorship?",
        required=True,
        options=("Yes", "No"),
        disqualifying=True,
    )

    answer = resolve_question(
        question,
        load_facts(FACTS_PATH),
        kb,
        llm=llm,
        pii=kb.identity,
    )

    assert answer.answer == "No"
    assert answer.source == "fact"
    assert answer.status == "answered"
    assert llm.calls == 0


def test_missing_required_fact_blocks_and_missing_optional_fact_is_skipped(kb):
    required = resolve_question(
        FormQuestion(
            key="start-date-required",
            label="When can you start?",
            required=True,
        ),
        ApprovedFacts(facts={}),
        kb,
        llm=FakeAnswerLLM(),
        pii=kb.identity,
    )
    optional = resolve_question(
        FormQuestion(
            key="start-date-optional",
            label="When can you start?",
            required=False,
        ),
        ApprovedFacts(facts={}),
        kb,
        llm=FakeAnswerLLM(),
        pii=kb.identity,
    )

    assert required.status == "blocked"
    assert optional.status == "skipped"
    assert optional.answer is None
    assert optional.source == "unresolved"


def test_unknown_required_question_blocks_but_optional_unknown_is_skipped(kb):
    required = FormQuestion(
        key="unknown-required",
        label="What is your favorite programming language?",
        required=True,
    )
    optional = FormQuestion(
        key="unknown-optional",
        label="What is your favorite programming language?",
        required=False,
    )
    llm = FakeAnswerLLM()

    required_answer = resolve_question(
        required, ApprovedFacts(facts={}), kb, llm=llm, pii=kb.identity
    )
    optional_answer = resolve_question(
        optional, ApprovedFacts(facts={}), kb, llm=llm, pii=kb.identity
    )

    assert required_answer.status == "blocked"
    assert optional_answer.status == "skipped"
    assert llm.calls == 0


@pytest.mark.parametrize(
    "label",
    [
        "Why are you interested in this role?",
        "Describe your relevant experience",
    ],
)
def test_subjective_question_inference_uses_redacted_knowledge_base(kb, label):
    llm = FakeAnswerLLM()
    kb_with_pii_in_summary = replace(
        kb,
        summary=f"{kb.summary} Contact {kb.identity.full_name} at {kb.identity.email}.",
    )
    question = FormQuestion(
        key="motivation",
        label=label,
        required=True,
    )

    answer = resolve_question(
        question,
        ApprovedFacts(facts={}),
        kb_with_pii_in_summary,
        llm=llm,
        pii=kb.identity,
    )

    prompt = llm.last_system + llm.last_user
    assert answer.answer == "I have built Python services for internal users."
    assert answer.source == "llm"
    assert answer.status == "answered"
    assert llm.calls == 1
    assert not contains_pii(prompt, kb.identity)


def test_pii_returned_by_inference_is_blocked_and_not_kept(kb):
    llm = FakeAnswerLLM({"answer": f"Contact {kb.identity.full_name}"})
    question = FormQuestion(
        key="motivation",
        label="Why are you interested in this role?",
        required=True,
    )

    answer = resolve_question(
        question,
        ApprovedFacts(facts={}),
        kb,
        llm=llm,
        pii=kb.identity,
    )

    assert answer.status == "blocked"
    assert answer.answer is None


def test_screen_questions_persists_metadata_but_returns_answer_text(session, opening_fixture, kb):
    application = upsert_application(
        session,
        opening_fixture.id,
        lane="review",
        status="awaiting_review",
        score=82,
        reasons=["Strong match"],
        red_flags=[],
    )
    questions = [
        FormQuestion(
            key="work-authorization",
            label="Are you legally authorized to work?",
            required=True,
            options=("Yes", "No"),
        ),
        FormQuestion(
            key="unknown-optional",
            label="What is your favorite programming language?",
            required=False,
        ),
    ]

    answers = screen_questions(
        session,
        application,
        questions,
        facts=load_facts(FACTS_PATH),
        kb=kb,
        llm=FakeAnswerLLM(),
        pii=kb.identity,
    )
    saved = session.exec(select(ApplicationAnswer).order_by(ApplicationAnswer.question_key)).all()

    assert [answer.answer for answer in answers] == ["Yes", None]
    assert [(row.question_key, row.source, row.status) for row in saved] == [
        ("unknown-optional", "unresolved", "skipped"),
        ("work-authorization", "fact", "answered"),
    ]
    assert "answer" not in ApplicationAnswer.__table__.columns
