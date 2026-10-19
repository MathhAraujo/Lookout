from datetime import UTC, datetime
from typing import Any

import httpx

from lookout.collectors.base import RawOpening
from lookout.config import Settings

_URL = "https://jobicy.com/api/v2/remote-jobs"


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

    company = item.get("companyName")
    title = item.get("jobTitle")
    url = item.get("url")
    if not all(isinstance(value, str) and value.strip() for value in (company, title, url)):
        return None

    location = item.get("jobGeo")
    description = item.get("jobDescription")
    external_id = item.get("id")
    return RawOpening(
        source="jobicy",
        external_id=str(external_id) if external_id is not None else None,
        company=company.strip(),
        title=title.strip(),
        location=location.strip() if isinstance(location, str) and location.strip() else None,
        url=url.strip(),
        description=description if isinstance(description, str) else "",
        posted_at=_parse_datetime(item.get("pubDate")),
        raw=dict(item),
    )


def parse_jobicy(payload: Any) -> list[RawOpening]:
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        return []

    jobs = []
    for item in payload["jobs"]:
        job = _parse_job(item)
        if job is not None:
            jobs.append(job)
    return jobs


class JobicyCollector:
    name = "jobicy"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self) -> list[RawOpening]:
        response = self.client.get(_URL)
        response.raise_for_status()
        return parse_jobicy(response.json())
