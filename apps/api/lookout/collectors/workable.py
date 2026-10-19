from dataclasses import replace
from typing import Any
from urllib.parse import quote

import httpx

from lookout.collectors.base import RawOpening
from lookout.config import Settings

_JOBS_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"
_JOB_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs/{shortcode}"
_JOBS_QUERY = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}


def parse_workable(payload: dict, slug: str, company: str) -> list[RawOpening]:
    results = payload.get("results")
    if not isinstance(results, list) or not company.strip():
        return []

    jobs = []
    for item in results:
        if not isinstance(item, dict):
            continue

        title = item.get("title")
        shortcode = item.get("shortcode")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(shortcode, str) or not shortcode.strip():
            continue

        city = item.get("city")
        country = item.get("country")
        location_parts = [
            part.strip()
            for part in (city, country)
            if isinstance(part, str) and part.strip()
        ]
        jobs.append(
            RawOpening(
                source="workable",
                external_id=shortcode.strip(),
                company=company.strip(),
                title=title.strip(),
                location=", ".join(location_parts) or None,
                url=(
                    f"https://apply.workable.com/{quote(slug, safe='')}/"
                    f"j/{quote(shortcode.strip(), safe='')}/"
                ),
                description="",
                posted_at=None,
                raw=dict(item),
            )
        )

    return jobs


def _workable_description(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""

    for key in ("description", "descriptionHtml", "description_html"):
        value = payload.get(key)
        if isinstance(value, str):
            return value

    nested_job = payload.get("job")
    if isinstance(nested_job, dict):
        return _workable_description(nested_job)
    return ""


class WorkableCollector:
    name = "workable"

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
            response = self.client.post(_JOBS_URL.format(slug=quote(slug, safe="")), json=_JOBS_QUERY)
            response.raise_for_status()
            openings = parse_workable(response.json(), slug, company)

            for opening in openings:
                detail_response = self.client.get(
                    _JOB_URL.format(
                        slug=quote(slug, safe=""),
                        shortcode=quote(opening.external_id or "", safe=""),
                    )
                )
                detail_response.raise_for_status()
                detail = detail_response.json()
                jobs.append(
                    replace(
                        opening,
                        description=_workable_description(detail),
                        raw={**opening.raw, "detail": detail},
                    )
                )

        return jobs
