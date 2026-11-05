"""API -> queue -> worker -> PDF acceptance with fictional facts and HTTP-stubbed inference."""

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from lookout.api import create_app, get_session
from lookout.collectors.base import RawOpening
from lookout.config import Settings
from lookout.llm import OpenRouterClient
from lookout.models import Job, Opening
from lookout.worker import process_next_job
from pypdf import PdfReader
from sqlmodel import select


def test_phase1_api_worker_pdf_contract(session, engine, tmp_path, monkeypatch):
    settings = Settings(
        database_url=engine.url.render_as_string(hide_password=False),
        kb_path=Path("tests/fixtures/kb"),
        artifacts_dir=tmp_path,
    )
    selection = json.loads(Path("tests/fixtures/tailor/selection_en.json").read_text())
    observed_prompts = []

    def inference(request):
        payload = json.loads(request.content)
        observed_prompts.append(payload["messages"])
        prompt = json.dumps(payload["messages"])
        for forbidden in (
            "Maria Silva",
            "maria.silva@example.com",
            "123.456.789-09",
            "Rua das Flores",
        ):
            assert forbidden not in prompt
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(selection)}}]}
        )

    class FictionalSource:
        name = "remoteok"

        def fetch(self):
            return [
                RawOpening(
                    source="remoteok",
                    external_id="fictional-acceptance",
                    company="Globex",
                    title="Backend Engineer",
                    location="Remote",
                    url="https://example.com/jobs/1",
                    description="We are looking for a developer with Python experience.",
                    posted_at=None,
                    raw={},
                )
            ]

    monkeypatch.setattr("lookout.worker.get_collector", lambda *args: FictionalSource())
    app = create_app(settings)

    def use_test_session():
        yield session

    app.dependency_overrides[get_session] = use_test_session
    try:
        with httpx.Client(transport=httpx.MockTransport(inference)) as transport:
            monkeypatch.setattr(
                "lookout.worker.OpenRouterClient",
                lambda **kwargs: OpenRouterClient(
                    api_key="fictional",
                    model="fictional",
                    client=transport,
                ),
            )
            with TestClient(app) as client:
                for _ in range(2):
                    response = client.post("/collect", json={"source": "remoteok"})
                    assert response.status_code == 202
                    assert process_next_job(session, settings)
                opening = session.exec(select(Opening)).one()
                response = client.post(f"/openings/{opening.id}/tailor")
                assert response.status_code == 202
                assert process_next_job(session, settings)
                assert all(job.status == "done" for job in session.exec(select(Job)))
                pdf = tmp_path / f"{opening.id}.pdf"
                text = " ".join(page.extract_text() for page in PdfReader(pdf).pages)
                assert "Maria Silva" in text and "maria.silva@example.com" in text
                assert "Built resilient API services" in text
                assert len(observed_prompts) == 1
    finally:
        app.state.engine.dispose()
