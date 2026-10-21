from datetime import UTC, datetime
from typing import Any

import httpx

from lookout.collectors.base import CollectorError, RawOpening
from lookout.config import Settings
from lookout.normalize import extract_application_email

_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def parse_greenhouse(payload: dict, company: str) -> list[RawOpening]:
    jobs_payload = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs_payload, list):
        raise CollectorError("Unexpected top-level payload from Greenhouse")
    if not company.strip():
        return []

    jobs = []
    for item in jobs_payload:
        if not isinstance(item, dict):
            continue

        title = item.get("title")
        url = item.get("absolute_url")
        if not all(isinstance(value, str) and value.strip() for value in (title, url)):
            continue

        location = item.get("location")
        location_name = location.get("name") if isinstance(location, dict) else None
        description = item.get("content")
        external_id = item.get("id")
        jobs.append(
            RawOpening(
                source="greenhouse",
                external_id=str(external_id) if external_id is not None else None,
                company=company.strip(),
                title=title.strip(),
                location=(
                    location_name.strip()
                    if isinstance(location_name, str) and location_name.strip()
                    else None
                ),
                url=url.strip(),
                description=description if isinstance(description, str) else "",
                posted_at=_parse_datetime(item.get("updated_at")),
                raw=dict(item),
                application_email=extract_application_email(
                    description if isinstance(description, str) else None,
                    apply_email_field=item.get("applyEmail"),
                ),
            )
        )

    return jobs


class GreenhouseCollector:
    name = "greenhouse"

    def __init__(
        self,
        settings: Settings,
        companies: dict[str, str],
        client: httpx.Client | None = None,
    ):
        self.settings = settings
        self.companies = companies
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self) -> list[RawOpening]:
        jobs = []
        for slug, company in self.companies.items():
            response = self.client.get(_URL.format(slug=slug), params={"content": "true"})
            response.raise_for_status()
            jobs.extend(parse_greenhouse(response.json(), company))
        return jobs
