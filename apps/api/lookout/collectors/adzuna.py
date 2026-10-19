from datetime import UTC, datetime
from typing import Any

import httpx

from lookout.collectors.base import CollectorError, RawOpening
from lookout.config import Settings

_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def parse_adzuna(payload: dict, country: str) -> list[RawOpening]:
    results = payload.get("results")
    if not isinstance(results, list):
        return []

    jobs = []
    for item in results:
        if not isinstance(item, dict):
            continue

        company = item.get("company")
        location = item.get("location")
        title = item.get("title")
        url = item.get("redirect_url")
        if not isinstance(company, dict):
            continue
        company_name = company.get("display_name")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (company_name, title, url)
        ):
            continue

        location_name = location.get("display_name") if isinstance(location, dict) else None
        description = item.get("description")
        external_id = item.get("id")
        jobs.append(
            RawOpening(
                source="adzuna",
                external_id=str(external_id) if external_id is not None else None,
                company=company_name.strip(),
                title=title.strip(),
                location=(
                    location_name.strip()
                    if isinstance(location_name, str) and location_name.strip()
                    else None
                ),
                url=url.strip(),
                description=description if isinstance(description, str) else "",
                posted_at=_parse_datetime(item.get("created")),
                raw={**item, "country": country},
            )
        )

    return jobs


class AdzunaCollector:
    name = "adzuna"

    def __init__(
        self,
        settings: Settings,
        countries: list[str],
        queries: list[str],
        client: httpx.Client | None = None,
    ):
        self.settings = settings
        self.countries = countries
        self.queries = queries
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self) -> list[RawOpening]:
        if not self.settings.adzuna_app_id or not self.settings.adzuna_app_key:
            raise CollectorError("Adzuna credentials are required to collect jobs")

        jobs = []
        for country in self.countries:
            for query in self.queries:
                response = self.client.get(
                    _URL.format(country=country),
                    params={
                        "app_id": self.settings.adzuna_app_id,
                        "app_key": self.settings.adzuna_app_key,
                        "results_per_page": 50,
                        "what": query,
                    },
                )
                response.raise_for_status()
                jobs.extend(parse_adzuna(response.json(), country))
        return jobs
