from calendar import timegm
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from lookout.collectors.base import RawOpening
from lookout.config import Settings

_URL = "https://himalayas.app/jobs/rss"


def _posted_at(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed")
    if parsed is None:
        return None
    try:
        return datetime.fromtimestamp(timegm(parsed), tz=UTC)
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _description(entry: Any) -> str:
    content = entry.get("content")
    if isinstance(content, list):
        for item in content:
            if (
                isinstance(item, dict)
                and isinstance(item.get("value"), str)
                and item["value"].strip()
            ):
                return item["value"]

    fallback = entry.get("description") or entry.get("summary")
    return fallback if isinstance(fallback, str) else ""


def parse_himalayas(payload: str) -> list[RawOpening]:
    feed = feedparser.parse(payload)
    jobs = []

    for entry in feed.entries:
        company = entry.get("himalayasjobs_companyname")
        title = entry.get("title")
        url = entry.get("link")
        if not all(isinstance(value, str) and value.strip() for value in (company, title, url)):
            continue

        location = entry.get("himalayasjobs_locationrestriction")
        external_id = entry.get("guid") or entry.get("id")
        jobs.append(
            RawOpening(
                source="himalayas",
                external_id=str(external_id) if external_id is not None else None,
                company=company.strip(),
                title=title.strip(),
                location=(
                    location.strip() if isinstance(location, str) and location.strip() else None
                ),
                url=url.strip(),
                description=_description(entry),
                posted_at=_posted_at(entry),
                raw=dict(entry),
            )
        )

    return jobs


class HimalayasCollector:
    name = "himalayas"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self) -> list[RawOpening]:
        response = self.client.get(_URL)
        response.raise_for_status()
        return parse_himalayas(response.text)
