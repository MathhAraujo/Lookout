import logging
import threading
import uuid
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session

from lookout.collectors.registry import build_collectors, get_collector, load_sources_config
from lookout.config import Settings, get_settings
from lookout.db import session_scope
from lookout.ingest import IngestStats, collect_all, collect_source
from lookout.llm import OpenRouterClient
from lookout.models import Job
from lookout.queue import claim_next, complete, enqueue, fail, reap_stale
from lookout.tailor.pipeline import tailor_resume

logger = logging.getLogger(__name__)


def handle_collect(session: Session, settings: Settings, payload: dict) -> None:
    sources = load_sources_config(settings.sources_config)
    source = payload.get("source")
    if source:
        source_config = sources.get(source)
        if source_config is None:
            raise ValueError(f"Unknown collection source: {source}")
        stats = collect_source(session, get_collector(source, settings, source_config), settings)
        _raise_collection_errors({source: stats})
        return

    stats = collect_all(session, build_collectors(settings, sources), settings)
    _raise_collection_errors(stats)


def _raise_collection_errors(results: dict[str, IngestStats]) -> None:
    errors = [f"{name}: {', '.join(stats.errors)}" for name, stats in results.items() if stats.errors]
    if errors:
        raise RuntimeError("; ".join(errors))


def handle_tailor(session: Session, settings: Settings, payload: dict) -> None:
    opening_id = uuid.UUID(str(payload["opening_id"]))
    llm = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_tailoring_model,
    )
    tailor_resume(
        session,
        opening_id=opening_id,
        kb_path=settings.kb_path,
        out_dir=settings.artifacts_dir,
        llm=llm,
    )


JobHandler = Callable[[Session, Settings, dict], None]
JOB_HANDLERS: dict[str, JobHandler] = {
    "collect": handle_collect,
    "tailor": handle_tailor,
}


def process_next_job(session: Session, settings: Settings) -> bool:
    job = claim_next(session)
    if job is None:
        return False

    job_id = job.id
    job_type = job.type
    payload = dict(job.payload)
    session.commit()

    try:
        handler = JOB_HANDLERS.get(job_type)
        if handler is None:
            raise RuntimeError(f"No handler registered for job type: {job_type}")
        handler(session, settings, payload)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        failed_job = session.get(Job, job_id)
        if failed_job is not None:
            fail(session, failed_job, str(exc))
            session.commit()
        return True

    completed_job = session.get(Job, job_id)
    if completed_job is not None:
        complete(session, completed_job)
        session.commit()
    return True


def enqueue_collect_job(settings: Settings, source: str) -> None:
    with session_scope(settings) as session:
        enqueue(session, "collect", {"source": source})


def _poll_queue(settings: Settings) -> None:
    with session_scope(settings) as session:
        process_next_job(session, settings)


def _reap_stale_jobs(settings: Settings) -> None:
    with session_scope(settings) as session:
        reaped = reap_stale(session)
    if reaped:
        logger.warning("Requeued %s stale jobs", reaped)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    sources = load_sources_config(settings.sources_config)
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _poll_queue,
        "interval",
        args=[settings],
        seconds=settings.worker_poll_seconds,
        max_instances=1,
        id="queue-poll",
        replace_existing=True,
    )
    scheduler.add_job(
        _reap_stale_jobs,
        "interval",
        args=[settings],
        minutes=10,
        id="reap-stale-jobs",
        replace_existing=True,
    )
    for source, source_config in sources.items():
        if source_config.get("enabled", False):
            scheduler.add_job(
                enqueue_collect_job,
                "interval",
                args=[settings, source],
                minutes=source_config["interval_minutes"],
                id=f"enqueue-{source}",
                replace_existing=True,
            )

    scheduler.start()
    logger.info("worker started")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
