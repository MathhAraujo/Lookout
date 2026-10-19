import json
from pathlib import Path

from lookout.tailor.render import render_resume_html
from lookout.tailor.schema import TailoredResume


def test_render_localizes_headings_and_uses_kb_identity(kb):
    response_path = Path("tests/fixtures/tailor/llm_response_ptbr.json")
    resume = TailoredResume.model_validate(json.loads(response_path.read_text()))

    html = render_resume_html(resume, kb)

    assert "Experiência" in html and "Maria Silva" in html
