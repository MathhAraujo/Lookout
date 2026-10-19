import json
from pathlib import Path

from lookout.collectors.himalayas import parse_himalayas
from lookout.collectors.weworkremotely import parse_weworkremotely
from lookout.collectors.workingnomads import parse_workingnomads


def test_parse_weworkremotely_splits_company_and_title():
    xml = Path("tests/fixtures/sources/weworkremotely.xml").read_text()
    jobs = parse_weworkremotely(xml)

    assert [job.company for job in jobs] == ["Globex", "Initech"]
    assert jobs[0].title == "Senior Python Engineer"
    assert jobs[0].location == "Anywhere in the World"
    assert jobs[0].source == "weworkremotely"
    assert jobs[0].external_id == "wwr-123" and jobs[0].posted_at is not None


def test_parse_workingnomads_maps_fields_and_skips_malformed_entries():
    payload = json.loads(Path("tests/fixtures/sources/workingnomads.json").read_text())
    jobs = parse_workingnomads(payload)

    assert [job.company for job in jobs] == ["Globex", "Initech"]
    assert jobs[0].title == "Senior Python Engineer" and jobs[0].source == "workingnomads"
    assert jobs[0].external_id == "wn-123" and jobs[0].posted_at is not None
    assert jobs[0].location == "Worldwide"
    assert jobs[0].url == "https://www.workingnomads.com/jobs/wn-123"
    assert "fictional products" in jobs[0].description


def test_parse_himalayas_uses_namespaced_fields_and_encoded_content():
    xml = Path("tests/fixtures/sources/himalayas.xml").read_text()
    jobs = parse_himalayas(xml)

    assert [job.company for job in jobs] == ["Globex", "Initech"]
    assert jobs[0].title == "Senior Python Engineer" and jobs[0].source == "himalayas"
    assert jobs[0].location == "Worldwide"
    assert "Detailed fictional role description" in jobs[0].description
    assert jobs[1].description == "Fallback description for a fictional role."
    assert jobs[0].external_id == "himalayas-123" and jobs[0].posted_at is not None
