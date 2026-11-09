from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, select

from lookout.collectors.base import Collector, RawOpening
from lookout.config import Settings
from lookout.dedup import is_duplicate
from lookout.models import Opening
from lookout.normalize import dedup_key
from lookout.openings import insert_opening, list_dedup_keys


@dataclass
class IngestStats:
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    inserted_ids: list[UUID] = field(default_factory=list)


def ingest(
    session: Session,
    raws: Iterable[RawOpening],
    *,
    company_threshold: float = 90.0,
    title_threshold: float = 90.0,
) -> IngestStats:
    stats = IngestStats()
    # Fetches happen before this transaction lock. Serialize the small local
    # ingestion workload so cross-source fuzzy decisions see committed inserts.
    session.execute(text("SELECT pg_advisory_xact_lock(1280266068)"))
    known_keys = list_dedup_keys(session)
    exact_keys = set(known_keys)
    known_ids = set(session.exec(select(Opening.source, Opening.external_id)).all())

    for raw in raws:
        stats.fetched += 1
        if not raw.company.strip() or not raw.title.strip() or not raw.url.strip():
            stats.skipped += 1
            continue

        key = dedup_key(raw.company, raw.title)
        if (
            (raw.external_id is not None and (raw.source, raw.external_id) in known_ids)
            or key in exact_keys
            or is_duplicate(
                key,
                known_keys,
                company_threshold=company_threshold,
                title_threshold=title_threshold,
            )
        ):
            stats.duplicates += 1
            continue

        opening = insert_opening(session, raw)
        opening.dedup_key = key
        session.add(opening)
        session.flush()
        known_keys.append(key)
        exact_keys.add(key)
        known_ids.add((raw.source, raw.external_id))
        stats.inserted += 1
        stats.inserted_ids.append(opening.id)

    return stats


def collect_source(session: Session, collector: Collector, settings: Settings) -> IngestStats:
    try:
        raws = collector.fetch()
    except Exception as exc:  # noqa: BLE001
        return IngestStats(errors=[f"Collection failed ({type(exc).__name__})"])

    stats = ingest(
        session,
        raws,
        company_threshold=settings.dedup_company_threshold,
        title_threshold=settings.dedup_title_threshold,
    )
    if settings.workflow_enabled:
        from lookout.workflow import enqueue_matches

        enqueue_matches(session, stats.inserted_ids)
    return stats


def collect_all(
    session: Session,
    collectors: Iterable[Collector],
    settings: Settings,
) -> dict[str, IngestStats]:
    results: dict[str, IngestStats] = {}

    for collector in collectors:
        try:
            with session.begin_nested():
                results[collector.name] = collect_source(session, collector, settings)
        except Exception as exc:  # noqa: BLE001
            results[collector.name] = IngestStats(
                errors=[f"Collection failed ({type(exc).__name__})"]
            )

    return results
