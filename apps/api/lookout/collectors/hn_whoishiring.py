from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

import httpx

from lookout.collectors.base import CollectorError, RawOpening
from lookout.config import Settings

_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_ITEM_URL = "https://hn.algolia.com/api/v1/items/{}"
_HN_ITEM_URL = "https://news.ycombinator.com/item?id={}"


class _CommentHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "div", "li", "p"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"div", "li", "p"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _first_line(text: str) -> str:
    parser = _CommentHTMLParser()
    parser.feed(text)
    return next((line.strip() for line in "".join(parser.parts).splitlines() if line.strip()), "")


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def parse_hn_thread(item: dict, story_title: str) -> list[RawOpening]:
    children = item.get("children") if isinstance(item, dict) else None
    if not isinstance(children, list):
        raise CollectorError("Unexpected top-level payload for HN thread")

    jobs = []
    for comment in children:
        if not isinstance(comment, dict):
            continue
        comment_id = comment.get("id")
        text = comment.get("text")
        if comment_id is None or not isinstance(text, str):
            continue

        parts = [part.strip() for part in _first_line(text).split("|")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            continue

        location = parts[2] if len(parts) > 2 and parts[2] else None
        jobs.append(
            RawOpening(
                source="hn_whoishiring",
                external_id=str(comment_id),
                company=parts[0],
                title=parts[1],
                location=location,
                url=_HN_ITEM_URL.format(comment_id),
                description=text,
                posted_at=_parse_datetime(comment.get("created_at")),
                raw={"story_title": story_title, "comment_id": str(comment_id)},
            )
        )

    return jobs


class HnWhoIsHiringCollector:
    name = "hn_whoishiring"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=30.0)

    def fetch(self) -> list[RawOpening]:
        response = self.client.get(
            _SEARCH_URL,
            params={"tags": "story,author_whoishiring", "query": '"who is hiring"'},
        )
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not isinstance(hits, list):
            raise CollectorError("Unexpected top-level payload from HN search")

        valid_hits = [
            hit
            for hit in hits
            if isinstance(hit, dict)
            and hit.get("objectID") is not None
            and isinstance(hit.get("title"), str)
        ]
        if hits and not valid_hits:
            raise CollectorError("Unexpected story entries in HN search response")
        if not valid_hits:
            return []

        latest = max(valid_hits, key=lambda hit: int(hit.get("created_at_i") or 0))
        story_id = str(latest["objectID"])
        item_response = self.client.get(_ITEM_URL.format(story_id))
        item_response.raise_for_status()
        return parse_hn_thread(item_response.json(), latest["title"])
