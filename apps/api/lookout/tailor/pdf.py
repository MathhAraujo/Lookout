import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from weasyprint import HTML


def html_to_pdf(html: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=out_path.parent, suffix=".pdf", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        HTML(string=html).write_pdf(target=str(temporary_path))
        os.replace(temporary_path, out_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return out_path
