from datetime import UTC, datetime
from typing import Any

import httpx

from lookout.collectors.base import RawOpening
from lookout.config import Settings

_URL = "https://www.arbeitnow.com/api/job-board-api"


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _parse_job(item: Any) -> RawOpening | None:
    if not isinstance(item, dict):
        return None

    company = item.get("company_name")
    title = item.get("title")
    url = item.get("url")
    if not all(isinstance(value, str) and value.strip() for value in (company, title, url)):
        return None

    location = item.get("location")
    description = item.get("description")
    external_id = item.get("slug")
    return RawOpening(
        source="arbeitnow",
        external_id=str(external_id) if external_id is not None else None,
        company=company.strip(),
        title=title.strip(),
        location=location.strip() if isinstance(location, str) and location.strip() else None,
        url=url.strip(),
        description=description if isinstance(description, str) else "",
        posted_at=_parse_timestamp(item.get("created_at")),
        raw=dict(item),
    )


def parse_arbeitnow(payload: Any) -> list[RawOpening]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return []

    jobs = []
    for item in payload["data"]:
        job = _parse_job(item)
        if job is not None:
            jobs.append(job)
    return jobs


class ArbeitnowCollector:
    name = "arbeitnow"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self) -> list[RawOpening]:
        response = self.client.get(_URL)
        response.raise_for_status()
        return parse_arbeitnow(response.json())
