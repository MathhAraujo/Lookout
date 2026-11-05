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


def test_successful_atomic_render_preserves_existing_pdf_permissions(tmp_path, monkeypatch):
    target = tmp_path / "resume.pdf"
    target.write_bytes(b"previous")
    target.chmod(0o600)

    def render(self, *, target):
        from pathlib import Path

        Path(target).write_bytes(b"complete")

    monkeypatch.setattr("lookout.tailor.pdf.HTML.write_pdf", render)
    html_to_pdf("<p>Fictional resume</p>", target)
    assert target.read_bytes() == b"complete"
    assert target.stat().st_mode & 0o777 == 0o600
    new_target = tmp_path / "new.pdf"
    html_to_pdf("<p>Fictional resume</p>", new_target)
    assert new_target.stat().st_mode & 0o444 == 0o444
