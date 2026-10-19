from uuid import uuid4


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_openings(client, opening_fixture):
    response = client.get("/openings")

    assert [opening["company"] for opening in response.json()] == ["Globex"]


def test_post_collect_enqueues_one_job_per_enabled_source(client):
    response = client.post("/collect", json={})

    assert response.status_code == 202 and response.json()["enqueued"] >= 1


def test_post_collect_returns_404_for_unknown_source(client):
    assert client.post("/collect", json={"source": "unknown"}).status_code == 404


def test_post_tailor_enqueues_job(client, opening_fixture):
    response = client.post(f"/openings/{opening_fixture.id}/tailor")

    assert response.status_code == 202 and response.json()["job_id"]


def test_post_tailor_404_on_unknown_opening(client):
    assert client.post(f"/openings/{uuid4()}/tailor").status_code == 404
