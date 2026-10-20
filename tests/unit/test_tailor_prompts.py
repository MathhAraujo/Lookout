from pathlib import Path
from types import SimpleNamespace

from lookout.kb import kb_to_prompt_text, load_knowledge_base
from lookout.tailor.prompts import build_tailor_prompt


def test_prompt_contains_guardrail_redacted_kb_and_posting():
    kb = load_knowledge_base(Path("tests/fixtures/kb"))
    opening = SimpleNamespace(
        company="Globex",
        title="Senior Python Engineer",
        description="Build fictional APIs with Python.",
    )

    system, user = build_tailor_prompt(
        opening=opening,
        kb_text=kb_to_prompt_text(kb),
        language="en",
    )

    assert "Never invent" in system and "English" in system
    assert "[exp-acme]" in user and opening.title in user and opening.company in user


def test_prompt_specifies_the_tailored_resume_json_fields():
    system, _ = build_tailor_prompt(
        opening=SimpleNamespace(company="Globex", title="Engineer", description="Build APIs."),
        kb_text="[exp-acme] Fictional experience",
        language="en",
    )

    for field in (
        "language",
        "summary",
        "experiences",
        "projects",
        "skills",
        "kb_id",
        "highlights",
    ):
        assert f'"{field}"' in system


def test_prompt_requires_verbatim_knowledge_base_facts():
    system, _ = build_tailor_prompt(
        opening=SimpleNamespace(company="Globex", title="Engineer", description="Build APIs."),
        kb_text="[exp-acme] Fictional experience",
        language="en",
    )

    assert "summary must be copied verbatim from a KB fact" in system
    assert "highlights must be copied verbatim from that item's KB highlights" in system
