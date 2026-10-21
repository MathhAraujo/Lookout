from datetime import UTC, datetime
from typing import Any

import httpx

from lookout.collectors.base import CollectorError, RawOpening
from lookout.config import Settings
from lookout.normalize import extract_application_email

_URL = "https://api.lever.co/v0/postings/{slug}"


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def parse_lever(payload: list[dict], company: str) -> list[RawOpening]:
    if not isinstance(payload, list):
        raise CollectorError("Unexpected top-level payload from Lever")
    if not company.strip():
        return []

    jobs = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        title = item.get("text")
        url = item.get("hostedUrl")
        if not all(isinstance(value, str) and value.strip() for value in (title, url)):
            continue

        categories = item.get("categories")
        location = categories.get("location") if isinstance(categories, dict) else None
        description = item.get("descriptionPlain")
        external_id = item.get("id")
        html_content = item.get("content")
        jobs.append(
            RawOpening(
                source="lever",
                external_id=str(external_id) if external_id is not None else None,
                company=company.strip(),
                title=title.strip(),
                location=location.strip()
                if isinstance(location, str) and location.strip()
                else None,
                url=url.strip(),
                description=description if isinstance(description, str) else "",
                posted_at=_parse_timestamp(item.get("createdAt")),
                raw=dict(item),
                application_email=extract_application_email(
                    html_content if isinstance(html_content, str) else None,
                    apply_email_field=item.get("applyEmail"),
                ),
            )
        )

    return jobs


class LeverCollector:
    name = "lever"

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
            response = self.client.get(_URL.format(slug=slug))
            response.raise_for_status()
            jobs.extend(parse_lever(response.json(), company))
        return jobs
