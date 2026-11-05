import json
from pathlib import Path

import pytest
from lookout.kb import load_knowledge_base
from lookout.redaction import contains_pii
from lookout.tailor.pipeline import TailorError, detect_language, tailor_resume
from pypdf import PdfReader

KB_FIXTURE = Path("tests/fixtures/kb")
SELF_PII = load_knowledge_base(KB_FIXTURE).identity


def load_json(name: str) -> dict:
    path = Path("tests/fixtures/tailor") / name
    return json.loads(path.read_text())


class FakeLLM:
    def __init__(self, response: dict):
        self._response = response

    def complete_json(self, *, system: str, user: str) -> dict:
        assert not contains_pii(system + user, SELF_PII)
        return self._response


def test_tailor_resume_produces_real_text_pdf(tmp_path, session, opening_fixture):
    pdf_path = tailor_resume(
        session,
        opening_id=opening_fixture.id,
        kb_path=KB_FIXTURE,
        out_dir=tmp_path,
        llm=FakeLLM(load_json("selection_en.json")),
    )

    text = PdfReader(str(pdf_path)).pages[0].extract_text()
    assert "Experience" in text and "Maria Silva" in text


def test_tailor_resume_rejects_fabricated_llm_output(tmp_path, session, opening_fixture):
    with pytest.raises(TailorError):
        tailor_resume(
            session,
            opening_id=opening_fixture.id,
            kb_path=KB_FIXTURE,
            out_dir=tmp_path,
            llm=FakeLLM(load_json("llm_response_invalid.json")),
        )

    assert list(tmp_path.iterdir()) == []


def test_detect_language():
    assert detect_language("Vaga para desenvolvedor Python com experiência") == "pt-br"
    assert detect_language("We are looking for a Python developer with experience") == "en"


def test_portuguese_pipeline_renders_approved_body_and_fixed_header(
    tmp_path, session, opening_fixture
):
    opening_fixture.description = "Vaga para desenvolvedor com experiência em serviços de API"
    session.add(opening_fixture)
    session.flush()
    path = tailor_resume(
        session,
        opening_id=opening_fixture.id,
        kb_path=KB_FIXTURE,
        out_dir=tmp_path,
        llm=FakeLLM(load_json("selection_ptbr.json")),
    )
    text = " ".join(page.extract_text() for page in PdfReader(path).pages)
    assert "Maria Silva" in text and SELF_PII.email in text
    assert "Engenheira de Backend" in text and "Idiomas" in text
    assert "Backend Engineer" not in text and "Designed and maintained" not in text


@pytest.mark.parametrize(
    "field,value",
    [
        ("identity", {"full_name": "Changed Name"}),
        ("summary", "Invented content"),
        ("language", "pt-br"),
        ("skills", ["UnknownSkill"]),
        ("experiences", [{"kb_id": "exp-ghost", "highlights": [0]}]),
        ("experiences", [{"kb_id": "exp-acme", "highlights": [99]}]),
        ("experiences", [{"kb_id": "exp-acme", "highlights": [-1]}]),
        ("experiences", [{"kb_id": "exp-acme", "highlights": [True]}]),
        ("experiences", [{"kb_id": "exp-acme", "highlights": ["Invented text"]}]),
        ("experiences", [{"kb_id": "exp-acme", "highlights": [0, 0]}]),
    ],
)
def test_selection_cannot_change_header_or_author_facts(
    field,
    value,
    tmp_path,
    session,
    opening_fixture,
):
    selection = load_json("selection_en.json")
    selection[field] = value
    with pytest.raises(TailorError, match="invalid fact selection"):
        tailor_resume(
            session,
            opening_id=opening_fixture.id,
            kb_path=KB_FIXTURE,
            out_dir=tmp_path,
            llm=FakeLLM(selection),
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "personal_text",
    [
        "Maria  Silva",
        "Rua das Flores, 123",
        "(11) 98765 4321",
        "maria.silva@example.com",
    ],
)
def test_personal_data_in_body_is_blocked_before_inference(
    personal_text,
    tmp_path,
    session,
    opening_fixture,
):
    import shutil
    from unittest.mock import Mock

    kb_path = tmp_path / "kb"
    shutil.copytree(KB_FIXTURE, kb_path)
    (kb_path / "summary.md").write_text("Professional profile. " + personal_text)
    llm = Mock()
    with pytest.raises(TailorError, match="Personal data found"):
        tailor_resume(
            session,
            opening_id=opening_fixture.id,
            kb_path=kb_path,
            out_dir=tmp_path / "out",
            llm=llm,
        )
    llm.complete_json.assert_not_called()
    assert not (tmp_path / "out").exists()


def test_missing_translation_fails_before_inference(tmp_path, session, opening_fixture):
    import shutil
    from unittest.mock import Mock

    kb_path = tmp_path / "kb"
    shutil.copytree(KB_FIXTURE, kb_path)
    shutil.rmtree(kb_path / "translations")
    opening_fixture.description = "Vaga para desenvolvedor com experiência"
    session.add(opening_fixture)
    session.flush()
    llm = Mock()
    with pytest.raises(TailorError, match="Unable to load knowledge base"):
        tailor_resume(
            session,
            opening_id=opening_fixture.id,
            kb_path=kb_path,
            out_dir=tmp_path / "out",
            llm=llm,
        )
    llm.complete_json.assert_not_called()


def test_job_posting_personal_data_is_removed_from_inference(tmp_path, session, opening_fixture):
    opening_fixture.description += " Contact Maria  Silva at (11) 98765 4321, Rua das Flores, 123."
    session.add(opening_fixture)
    session.flush()
    tailor_resume(
        session,
        opening_id=opening_fixture.id,
        kb_path=KB_FIXTURE,
        out_dir=tmp_path,
        llm=FakeLLM(load_json("selection_en.json")),
    )
