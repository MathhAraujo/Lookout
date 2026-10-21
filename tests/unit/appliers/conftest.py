"""Shared fixtures for applier tests: a local HTTP site recording form POSTs."""

import http.server
import threading
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "appliers"


class _SubmitRecorder:
    def __init__(self) -> None:
        self.submission_posts = 0


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        name = self.path.split("?", 1)[0].lstrip("/")
        path = self.server.root / Path(name).name
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        self.server.recorder.submission_posts += 1
        name = self.path.split("?", 1)[0].lstrip("/")
        if name == "no-confirm":
            self.send_response(204)
            self.end_headers()
            return
        body = b"<html><body><p>Thank you - application received.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep test output clean
        pass


@pytest.fixture
def local_site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.root = FIXTURE_DIR
    server.recorder = _SubmitRecorder()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def base_url(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def resume_pdf(tmp_path):
    path = tmp_path / "resume.pdf"
    path.write_bytes(b"%PDF-1.4 fictional resume\n")
    return path
