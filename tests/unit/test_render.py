import json
from pathlib import Path

from lookout.tailor.render import render_resume_html
from lookout.tailor.schema import TailoredResume


def test_render_localizes_headings_and_uses_kb_identity(kb):
    response_path = Path("tests/fixtures/tailor/llm_response_ptbr.json")
    resume = TailoredResume.model_validate(json.loads(response_path.read_text()))

    html = render_resume_html(resume, kb)

    assert "Experiência" in html and "Maria Silva" in html


def test_header_stays_identical_across_body_selections(kb):
    import re

    from lookout.tailor.schema import ResumeSelection
    from lookout.tailor.validation import materialize_selection

    original = ResumeSelection(language="en", experiences=[], projects=[], skills=[])
    changed = original.model_copy(update={"skills": ["Python"]})
    first = render_resume_html(materialize_selection(original, kb, language="en"), kb)
    second = render_resume_html(materialize_selection(changed, kb, language="en"), kb)
    assert (
        re.search(r"<header.*?</header>", first, re.DOTALL).group()
        == re.search(r"<header.*?</header>", second, re.DOTALL).group()
    )
