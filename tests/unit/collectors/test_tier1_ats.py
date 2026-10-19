import json
from pathlib import Path

from lookout.collectors.greenhouse import parse_greenhouse
from lookout.collectors.lever import parse_lever
from lookout.collectors.workable import parse_workable


def load_fixture(name: str):
    path = Path("tests/fixtures/sources") / name
    return json.loads(path.read_text())


def test_parse_greenhouse_uses_configured_company_name():
    jobs = parse_greenhouse(load_fixture("greenhouse.json"), "Globex")

    assert [job.company for job in jobs] == ["Globex", "Globex"]
    assert jobs[0].title == "Senior Python Engineer"
    assert jobs[0].url.startswith("https://job-boards.greenhouse.io/")
    assert "<p>" in jobs[0].description
    assert jobs[0].source == "greenhouse" and jobs[0].posted_at is not None


def test_parse_lever_maps_fields():
    jobs = parse_lever(load_fixture("lever.json"), "Initech")

    assert [job.company for job in jobs] == ["Initech", "Initech"]
    assert jobs[0].title == "Backend Developer" and jobs[0].location == "São Paulo, Brazil"
    assert jobs[0].external_id == "lever-401" and jobs[0].posted_at is not None
    assert jobs[0].url == "https://jobs.lever.co/initech/lever-401"
    assert "fictional services" in jobs[0].description


def test_parse_workable_builds_apply_urls():
    jobs = parse_workable(load_fixture("workable.json"), "hooli", "Hooli")

    assert jobs[0].url == "https://apply.workable.com/hooli/j/9F8E7D6C5A/"
    assert jobs[0].external_id == "9F8E7D6C5A"
    assert jobs[0].company == "Hooli" and jobs[0].title == "Senior Python Engineer"
    assert jobs[0].location == "New York, United States"
