"""Exercise an isolated live API with a dedicated fixture-inference worker process.

Run only in the Phase 2 acceptance Compose project, with its regular worker stopped.
The HTTP fixture and child worker stay inside the API container. All data is fictional.
"""

import http.server
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
from lookout.config import get_settings
from lookout.db import session_scope
from lookout.models import Opening
from lookout.workflow import enqueue_matches
from pypdf import PdfReader

from tests.unit.appliers.conftest import _Handler


class FixtureHandler(_Handler):
    def do_POST(self):
        if self.path != "/chat/completions":
            return super().do_POST()
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        serialized = json.dumps(payload["messages"])
        assert "Maria Silva" not in serialized
        assert "maria.silva@example.com" not in serialized
        if payload["model"] == "fictional-scoring":
            title = json.loads(payload["messages"][1]["content"])["opening"]["title"]
            score = 85 if "Review" in title else 40 if "Reject" in title else 95
            result = {"score": score, "reasons": ["Fictional approved facts"], "red_flags": []}
        else:
            result = json.loads(Path("tests/fixtures/tailor/selection_en.json").read_text())
        response = json.dumps({"choices": [{"message": {"content": json.dumps(result)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


FIXTURE_WORKER = """
import os
from lookout import workflow, worker
from lookout.llm import OpenRouterClient

def client(**kwargs):
    return OpenRouterClient(api_key='fictional', model=kwargs['model'], base_url=os.environ['FIXTURE_URL'])

workflow.OpenRouterClient = client
workflow.build_scoring_client = lambda settings: client(model='fictional-scoring')
worker.main()
"""


def main():
    if os.getenv("LOOKOUT_ACCEPTANCE") != "true":
        raise SystemExit("This command requires the isolated acceptance Compose override")
    settings = get_settings()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    server.root = Path("tests/fixtures/appliers").resolve()
    server.recorder = SimpleNamespace(submission_posts=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with tempfile.TemporaryDirectory(prefix="lookout-stack-smoke-") as temporary:
            directory = Path(temporary)
            (directory / "sources.yml").write_text("sources: {}\n")
            (directory / "facts.yml").write_text(
                Path("tests/fixtures/facts/facts.yml")
                .read_text()
                .replace('"Yes"', '"Yes, authorized"')
            )
            environment = {
                **os.environ,
                "FIXTURE_URL": url,
                "WORKER_POLL_SECONDS": "1",
                "KB_PATH": "tests/fixtures/kb",
                "FACTS_PATH": str(directory / "facts.yml"),
                "SOURCES_CONFIG": str(directory / "sources.yml"),
                "BROWSER_PROFILES_PATH": str(directory / "profiles"),
                "OPENROUTER_API_KEY": "fictional",
                "OPENROUTER_SCORING_MODEL": "fictional-scoring",
                "OPENROUTER_TAILORING_MODEL": "fictional-tailoring",
                "DRY_RUN": "true",
                "AUTO_SUBMIT_ENABLED": "false",
            }
            openings = []
            with session_scope(settings) as session:
                for label, source in [
                    ("Auto", "greenhouse"),
                    ("Review", "greenhouse"),
                    ("Manual", "remoteok"),
                    ("Reject", "greenhouse"),
                ]:
                    opening = Opening(
                        source=source,
                        external_id=str(uuid4()),
                        company="Fictional Stack Smoke",
                        title=f"{label} Senior Python Engineer",
                        location="Remote",
                        url=url + "/greenhouse_form.html",
                        description="Build Python APIs with our remote team.",
                        dedup_key=str(uuid4()),
                    )
                    session.add(opening)
                    session.flush()
                    openings.append((label, str(opening.id)))
                enqueue_matches(session, [UUID(opening_id) for _, opening_id in openings])
            with (directory / "worker.log").open("w") as log:
                child = subprocess.Popen(
                    [sys.executable, "-c", FIXTURE_WORKER],
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as api:

                        def wait_for(predicate, timeout=90):
                            deadline = time.monotonic() + timeout
                            while time.monotonic() < deadline:
                                response = api.get("/applications")
                                response.raise_for_status()
                                items = {item["opening_id"]: item for item in response.json()}
                                if predicate(items):
                                    return items
                                if child.poll() is not None:
                                    raise AssertionError("fixture worker stopped before completion")
                                time.sleep(0.25)
                            raise AssertionError("timed out waiting for the fixture workflow")

                        expected = {
                            "Auto": "dry_run",
                            "Review": "awaiting_review",
                            "Manual": "manual_assist",
                            "Reject": "rejected",
                        }

                        def prepared(items):
                            for label, opening_id in openings:
                                item = items.get(opening_id)
                                if item is None or item["status"] != expected[label]:
                                    return False
                                artifacts = api.get(f"/applications/{item['id']}/artifacts").json()
                                if label != "Reject" and not any(
                                    a["kind"] == "resume" for a in artifacts
                                ):
                                    return False
                            return True

                        items = wait_for(prepared)
                        review_id = items[dict(openings)["Review"]]["id"]
                        assert api.post(f"/applications/{review_id}/approve").status_code == 200
                        assert api.post(f"/applications/{review_id}/approve").status_code == 409
                        items = wait_for(
                            lambda rows: (
                                rows.get(dict(openings)["Review"], {}).get("status") == "dry_run"
                            )
                        )
                        for label, opening_id in openings:
                            item = items[opening_id]
                            artifacts = api.get(f"/applications/{item['id']}/artifacts").json()
                            if label == "Reject":
                                assert artifacts == []
                            else:
                                resume = next(a for a in artifacts if a["kind"] == "resume")
                                response = api.get(f"/artifacts/{resume['id']}")
                                response.raise_for_status()
                                assert (
                                    "Maria Silva"
                                    in PdfReader(io.BytesIO(response.content))
                                    .pages[0]
                                    .extract_text()
                                )
                        assert server.recorder.submission_posts == 0
                        print(
                            json.dumps(
                                {
                                    "lanes": 4,
                                    "approved_review_status": "dry_run",
                                    "real_submissions": 0,
                                    "artifact_downloads": 3,
                                }
                            ),
                            flush=True,
                        )
                finally:
                    child.send_signal(signal.SIGINT)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
