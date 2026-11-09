"""Review controls, related opening data, and artifact delivery."""

import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from lookout.db import utcnow
from lookout.models import Application, ApplicationArtifact, Job
from sqlmodel import select


@pytest.fixture
def review(session, opening_fixture):
    application = Application(
        opening_id=opening_fixture.id,
        lane="review",
        status="awaiting_review",
        review_expires_at=utcnow() + timedelta(days=7),
        score=85,
    )
    session.add(application)
    session.flush()
    return application


def test_list_and_detail_include_source_link_with_filters(client, review, opening_fixture):
    response = client.get("/applications?lane=review&status=awaiting_review&limit=1&offset=0")
    assert response.status_code == 200
    item = response.json()[0]
    assert item["id"] == str(review.id)
    assert item["opening"]["company"] == "Globex"
    assert item["opening"]["url"] == opening_fixture.url
    assert client.get(f"/applications/{review.id}").json() == item
    assert client.get("/applications?lane=rejected").json() == []


def test_approval_enqueues_application_atomically_and_cannot_repeat(client, session, review):
    response = client.post(f"/applications/{review.id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert client.post(f"/applications/{review.id}/approve").status_code == 409
    jobs = list(session.exec(select(Job).where(Job.type == "apply")))
    assert len(jobs) == 1
    assert jobs[0].payload == {"application_id": str(review.id)}


def test_decline_keeps_application_available_for_manual_assistance(client, session, review):
    response = client.post(f"/applications/{review.id}/decline")
    assert response.status_code == 200
    assert response.json()["lane"] == "manual_assist"
    assert client.post(f"/applications/{review.id}/decline").status_code == 409
    assert session.exec(select(Job).where(Job.type == "apply")).one().payload == {
        "application_id": str(review.id)
    }


@pytest.mark.parametrize("action", ["", "/approve", "/decline", "/artifacts"])
def test_unknown_application_returns_404(client, action):
    request = client.post if action in {"/approve", "/decline"} else client.get
    assert request(f"/applications/{uuid4()}{action}").status_code == 404


def test_expired_review_cannot_be_approved_before_cleanup(client, session, review):
    review.review_expires_at = utcnow() - timedelta(seconds=1)
    session.flush()
    assert client.post(f"/applications/{review.id}/approve").status_code == 409
    assert list(session.exec(select(Job))) == []


def test_artifact_download_checks_integrity_and_hides_storage_key(
    client, session, review, monkeypatch
):
    from tests.workflow_helpers import MemoryArtifacts

    data = b"%PDF-fictional"
    artifact = ApplicationArtifact(
        application_id=review.id,
        kind="resume",
        object_key="private-key",
        content_type="application/pdf",
        sha256=hashlib.sha256(data).hexdigest(),
    )
    session.add(artifact)
    session.flush()
    store = MemoryArtifacts()
    store.objects["private-key"] = data
    monkeypatch.setattr("lookout.api.build_artifact_store", lambda settings: store)
    metadata = client.get(f"/applications/{review.id}/artifacts")
    assert metadata.status_code == 200
    assert "object_key" not in metadata.json()[0]
    response = client.get(f"/artifacts/{artifact.id}")
    assert response.content == data
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    store.objects["private-key"] = b"corrupt"
    assert client.get(f"/artifacts/{artifact.id}").status_code == 502
    assert client.get(f"/artifacts/{uuid4()}").status_code == 404


def test_connector_health_endpoint_is_available_without_live_checks(client):
    assert client.get("/connectors/health").json() == []
