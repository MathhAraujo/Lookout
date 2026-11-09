"""Fictional workflow services shared by integration and operational tests."""

import json
import os
from pathlib import Path

import httpx
from lookout.artifacts import ArtifactNotFoundError, S3ArtifactStore, ensure_bucket
from lookout.config import Settings
from lookout.llm import OpenRouterClient


class MemoryArtifacts:
    def __init__(self):
        self.objects = {}

    def put_file(self, *, key, path, content_type):
        self.objects[key] = Path(path).read_bytes()
        return key

    def get_bytes(self, key):
        if key not in self.objects:
            raise ArtifactNotFoundError("artifact not found")
        return self.objects[key]

    def delete(self, key):
        self.objects.pop(key, None)


def configure_workflow(monkeypatch, tmp_path, engine):
    settings = Settings(
        _env_file=None,
        database_url=engine.url.render_as_string(hide_password=False),
        workflow_enabled=True,
        kb_path=Path("tests/fixtures/kb"),
        facts_path=Path("tests/fixtures/facts/facts.yml"),
        match_profile_path=Path("templates/match-profile.yml"),
        openrouter_scoring_model="fictional-scoring",
        openrouter_tailoring_model="fictional-tailoring",
        artifacts_dir=tmp_path,
    )
    if os.getenv("TEST_MINIO_ENDPOINT_URL"):
        store = S3ArtifactStore(
            endpoint_url=os.environ["TEST_MINIO_ENDPOINT_URL"],
            bucket="lookout-workflow-test",
            access_key=os.environ["TEST_MINIO_ACCESS_KEY"],
            secret_key=os.environ["TEST_MINIO_SECRET_KEY"],
        )
        ensure_bucket(store.client, store.bucket)
    else:
        store = MemoryArtifacts()

    prompts = []

    def inference(request):
        payload = json.loads(request.content)
        messages = payload["messages"]
        prompts.append(messages)
        combined = json.dumps(messages)
        assert "Maria Silva" not in combined
        assert "maria.silva@example.com" not in combined
        if payload["model"] == "fictional-scoring":
            title = json.loads(messages[1]["content"])["opening"]["title"]
            score = 85 if "Review" in title else 40 if "Reject" in title else 95
            response = {"score": score, "reasons": ["Approved Python facts"], "red_flags": []}
        else:
            response = json.loads(Path("tests/fixtures/tailor/selection_en.json").read_text())
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(response)}}]}
        )

    def client(**kwargs):
        return OpenRouterClient(
            api_key="fictional",
            model=kwargs["model"],
            client=httpx.Client(transport=httpx.MockTransport(inference)),
        )

    monkeypatch.setattr("lookout.workflow.build_artifact_store", lambda settings: store)
    monkeypatch.setattr("lookout.workflow.OpenRouterClient", client)
    monkeypatch.setattr(
        "lookout.workflow.build_scoring_client",
        lambda settings: client(model=settings.openrouter_scoring_model),
    )
    return settings, store, prompts
