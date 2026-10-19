import json
from pathlib import Path

from lookout.collectors.adzuna import parse_adzuna
from lookout.collectors.hn_whoishiring import parse_hn_thread


def load_fixture(name: str):
    path = Path("tests/fixtures/sources") / name
    return json.loads(path.read_text())


def test_parse_adzuna_maps_results():
    jobs = parse_adzuna(load_fixture("adzuna.json"), "br")

    assert jobs[0].company == "Globex"
    assert jobs[0].title == "Senior Python Engineer"
    assert jobs[0].location == "São Paulo, Brazil"
    assert jobs[0].url == "https://www.adzuna.com.br/details/123"
    assert jobs[0].external_id == "123"
    assert jobs[0].source == "adzuna" and jobs[0].posted_at is not None


def test_parse_hn_thread_extracts_pipe_delimited_postings():
    item = load_fixture("hn_item.json")
    jobs = parse_hn_thread(item, "Ask HN: Who is hiring? (October 2026)")

    assert len(jobs) == 2
    assert jobs[0].company == "Globex" and jobs[0].title == "Senior Python Engineer"
    assert jobs[0].location == "Remote" and jobs[0].url.endswith("item?id=4411")
    assert jobs[0].external_id == "4411" and jobs[0].posted_at is not None
