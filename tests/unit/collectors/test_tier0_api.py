import json
from pathlib import Path

from lookout.collectors.arbeitnow import parse_arbeitnow
from lookout.collectors.jobicy import parse_jobicy
from lookout.collectors.remoteok import parse_remoteok
from lookout.collectors.remotive import parse_remotive


def load_fixture(name: str):
    path = Path("tests/fixtures/sources") / name
    return json.loads(path.read_text())


def test_parse_remoteok_maps_fields_and_skips_metadata():
    jobs = parse_remoteok(load_fixture("remoteok.json"))

    assert [job.company for job in jobs] == ["Globex", "Initech"]
    assert jobs[0].title == "Senior Python Engineer" and jobs[0].source == "remoteok"
    assert jobs[0].external_id == "123" and jobs[0].posted_at is not None
    assert jobs[0].location == "Anywhere"
    assert jobs[0].url == "https://remoteok.com/remote-jobs/123"
    assert "<p>" in jobs[0].description


def test_parse_remotive_maps_fields_and_skips_malformed_entries():
    jobs = parse_remotive(load_fixture("remotive.json"))

    assert [job.company for job in jobs] == ["Globex", "Initech"]
    assert jobs[0].title == "Senior Python Engineer" and jobs[0].source == "remotive"
    assert jobs[0].external_id == "234" and jobs[0].posted_at is not None
    assert jobs[0].location == "Worldwide"
    assert jobs[0].url == "https://remotive.com/remote-jobs/234"
    assert "fictional products" in jobs[0].description


def test_parse_arbeitnow_maps_fields_and_skips_malformed_entries():
    jobs = parse_arbeitnow(load_fixture("arbeitnow.json"))

    assert [job.company for job in jobs] == ["Globex", "Initech"]
    assert jobs[0].title == "Senior Python Engineer" and jobs[0].source == "arbeitnow"
    assert jobs[0].external_id == "globex-senior-python-engineer"
    assert jobs[0].posted_at is not None
    assert jobs[0].location == "Worldwide"
    assert jobs[0].url == "https://www.arbeitnow.com/view/globex-senior-python-engineer"
    assert "fictional products" in jobs[0].description


def test_parse_jobicy_maps_fields_and_skips_malformed_entries():
    jobs = parse_jobicy(load_fixture("jobicy.json"))

    assert [job.company for job in jobs] == ["Globex", "Initech"]
    assert jobs[0].title == "Senior Python Engineer" and jobs[0].source == "jobicy"
    assert jobs[0].external_id == "jobicy-345" and jobs[0].posted_at is not None
    assert jobs[0].location == "Worldwide"
    assert jobs[0].url == "https://jobicy.com/jobs/345"
    assert "fictional products" in jobs[0].description
