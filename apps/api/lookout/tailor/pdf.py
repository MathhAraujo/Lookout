from pathlib import Path

from weasyprint import HTML


def html_to_pdf(html: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(target=str(out_path))
    return out_path
