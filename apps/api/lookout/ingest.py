from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlmodel import Session

from lookout.collectors.base import Collector, RawOpening
from lookout.config import Settings
from lookout.dedup import is_duplicate
from lookout.normalize import dedup_key
from lookout.openings import insert_opening, list_dedup_keys


@dataclass
class IngestStats:
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def ingest(
    session: Session,
    raws: Iterable[RawOpening],
    *,
    company_threshold: float = 90.0,
    title_threshold: float = 90.0,
) -> IngestStats:
    stats = IngestStats()
    known_keys = list_dedup_keys(session)

    for raw in raws:
        stats.fetched += 1
        if not raw.company.strip() or not raw.title.strip() or not raw.url.strip():
            stats.skipped += 1
            continue

        key = dedup_key(raw.company, raw.title)
        if key in known_keys or is_duplicate(
            key,
            known_keys,
            company_threshold=company_threshold,
            title_threshold=title_threshold,
        ):
            stats.duplicates += 1
            continue

        opening = insert_opening(session, raw)
        opening.dedup_key = key
        session.add(opening)
        session.flush()
        known_keys.append(key)
        stats.inserted += 1

    return stats


def collect_source(session: Session, collector: Collector, settings: Settings) -> IngestStats:
    try:
        raws = collector.fetch()
    except Exception as exc:  # noqa: BLE001
        return IngestStats(errors=[str(exc)])

    return ingest(
        session,
        raws,
        company_threshold=settings.dedup_company_threshold,
        title_threshold=settings.dedup_title_threshold,
    )


def collect_all(
    session: Session,
    collectors: Iterable[Collector],
    settings: Settings,
) -> dict[str, IngestStats]:
    results: dict[str, IngestStats] = {}

    for collector in collectors:
        try:
            results[collector.name] = collect_source(session, collector, settings)
        except Exception as exc:  # noqa: BLE001
            results[collector.name] = IngestStats(errors=[str(exc)])

    return results
