from calendar import timegm
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from lookout.collectors.base import RawOpening
from lookout.config import Settings

_URL = "https://weworkremotely.com/remote-jobs.rss"


def _posted_at(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed")
    if parsed is None:
        return None
    try:
        return datetime.fromtimestamp(timegm(parsed), tz=UTC)
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def parse_weworkremotely(payload: str) -> list[RawOpening]:
    feed = feedparser.parse(payload)
    jobs = []

    for entry in feed.entries:
        title = entry.get("title")
        url = entry.get("link")
        if not isinstance(title, str) or ": " not in title or not isinstance(url, str):
            continue

        company, role = title.split(": ", 1)
        if not company.strip() or not role.strip() or not url.strip():
            continue

        location = entry.get("region")
        description = entry.get("description") or entry.get("summary") or ""
        external_id = entry.get("guid") or entry.get("id")
        jobs.append(
            RawOpening(
                source="weworkremotely",
                external_id=str(external_id) if external_id is not None else None,
                company=company.strip(),
                title=role.strip(),
                location=(
                    location.strip()
                    if isinstance(location, str) and location.strip()
                    else None
                ),
                url=url.strip(),
                description=description if isinstance(description, str) else "",
                posted_at=_posted_at(entry),
                raw=dict(entry),
            )
        )

    return jobs


class WeWorkRemotelyCollector:
    name = "weworkremotely"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self) -> list[RawOpening]:
        response = self.client.get(_URL)
        response.raise_for_status()
        return parse_weworkremotely(response.text)
