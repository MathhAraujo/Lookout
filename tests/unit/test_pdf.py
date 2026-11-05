import pytest
from lookout.tailor.pdf import html_to_pdf


def test_failed_render_preserves_previous_pdf_and_cleans_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "resume.pdf"
    target.write_bytes(b"previous-approved-pdf")

    def fail_render(self, *, target):
        from pathlib import Path

        Path(target).write_bytes(b"incomplete-pdf")
        raise RuntimeError("Renderer failed")

    monkeypatch.setattr("lookout.tailor.pdf.HTML.write_pdf", fail_render)
    with pytest.raises(RuntimeError):
        html_to_pdf("<p>Fictional resume</p>", target)
    assert target.read_bytes() == b"previous-approved-pdf"
    assert list(tmp_path.iterdir()) == [target]
