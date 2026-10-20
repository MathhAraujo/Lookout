from datetime import UTC, datetime
from typing import Any

import httpx

from lookout.collectors.base import CollectorError, RawOpening
from lookout.config import Settings

_URL = "https://remoteok.com/api"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _parse_job(item: Any) -> RawOpening | None:
    if not isinstance(item, dict):
        return None

    company = item.get("company")
    title = item.get("position")
    url = item.get("url")
    if not all(isinstance(value, str) and value.strip() for value in (company, title, url)):
        return None

    location = item.get("location")
    description = item.get("description")
    external_id = item.get("id")
    return RawOpening(
        source="remoteok",
        external_id=str(external_id) if external_id is not None else None,
        company=company.strip(),
        title=title.strip(),
        location=location.strip() if isinstance(location, str) and location.strip() else None,
        url=url.strip(),
        description=description if isinstance(description, str) else "",
        posted_at=_parse_datetime(item.get("date")),
        raw=dict(item),
    )


def parse_remoteok(payload: Any) -> list[RawOpening]:
    if not isinstance(payload, list):
        raise CollectorError("Unexpected top-level payload from RemoteOK")

    jobs = []
    for item in payload[1:]:
        job = _parse_job(item)
        if job is not None:
            jobs.append(job)
    return jobs


class RemoteOKCollector:
    name = "remoteok"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self) -> list[RawOpening]:
        response = self.client.get(_URL, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        return parse_remoteok(response.json())
