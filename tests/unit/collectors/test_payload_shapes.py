from types import SimpleNamespace

import pytest
from lookout.collectors.adzuna import parse_adzuna
from lookout.collectors.arbeitnow import parse_arbeitnow
from lookout.collectors.base import CollectorError
from lookout.collectors.greenhouse import parse_greenhouse
from lookout.collectors.hn_whoishiring import HnWhoIsHiringCollector, parse_hn_thread
from lookout.collectors.jobicy import parse_jobicy
from lookout.collectors.lever import parse_lever
from lookout.collectors.remoteok import parse_remoteok
from lookout.collectors.remotive import parse_remotive
from lookout.collectors.workable import parse_workable
from lookout.collectors.workingnomads import parse_workingnomads


@pytest.mark.parametrize(
    ("parser", "args"),
    [
        pytest.param(parse_remoteok, ({"jobs": []},), id="remoteok"),
        pytest.param(parse_workingnomads, ({"jobs": []},), id="workingnomads"),
        pytest.param(parse_remotive, ({},), id="remotive"),
        pytest.param(parse_arbeitnow, ({},), id="arbeitnow"),
        pytest.param(parse_jobicy, ({},), id="jobicy"),
        pytest.param(parse_adzuna, ({}, "br"), id="adzuna"),
        pytest.param(parse_lever, ({}, "Globex"), id="lever"),
        pytest.param(parse_greenhouse, ({}, "Globex"), id="greenhouse"),
        pytest.param(parse_workable, ({}, "hooli", "Hooli"), id="workable"),
        pytest.param(parse_hn_thread, ({}, "Ask HN: Who is Hiring"), id="hn-whoishiring"),
    ],
)
def test_collectors_raise_for_unexpected_top_level_payload(parser, args):
    with pytest.raises(CollectorError):
        parser(*args)


class _JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _SearchClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, params=None):
        return _JsonResponse(self.payload)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-hits"),
        pytest.param({"hits": "unexpected"}, id="non-list-hits"),
        pytest.param({"hits": [{}]}, id="invalid-story-entries"),
    ],
)
def test_hn_collector_raises_for_unexpected_search_shape(payload):
    collector = HnWhoIsHiringCollector(SimpleNamespace(), client=_SearchClient(payload))

    with pytest.raises(CollectorError):
        collector.fetch()
