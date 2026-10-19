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
        llm=FakeLLM(load_json("llm_response_en.json")),
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
