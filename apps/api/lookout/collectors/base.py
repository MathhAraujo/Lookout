from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class RawOpening:
    source: str
    external_id: str | None
    company: str
    title: str
    location: str | None
    url: str
    description: str
    posted_at: datetime | None
    raw: dict


class Collector(Protocol):
    name: str

    def fetch(self) -> list[RawOpening]: ...


class CollectorError(Exception):
    pass
