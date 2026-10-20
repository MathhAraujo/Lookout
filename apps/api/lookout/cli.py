import argparse
import json
from dataclasses import asdict
from uuid import UUID

from lookout.collectors.linkedin_email import run_gmail_auth
from lookout.collectors.registry import build_collectors, get_collector, load_sources_config
from lookout.config import get_settings
from lookout.db import session_scope
from lookout.ingest import collect_all, collect_source
from lookout.llm import OpenRouterClient
from lookout.openings import list_openings
from lookout.tailor.pipeline import tailor_resume
from lookout.worker import enqueue_collect_job


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lookout")
    commands = parser.add_subparsers(dest="command", required=True)

    collect_parser = commands.add_parser("collect", help="Collect job openings")
    collect_parser.add_argument("--source", help="Collect from one configured source")
    collect_parser.add_argument(
        "--enqueue",
        action="store_true",
        help="Add collection jobs to the worker queue instead of running synchronously",
    )

    tailor_parser = commands.add_parser("tailor", help="Generate a tailored resume PDF")
    tailor_parser.add_argument("opening_id", help="UUID of the opening to tailor for")

    commands.add_parser("gmail-auth", help="Authorize read-only Gmail access")

    openings_parser = commands.add_parser("list-openings", help="List collected openings")
    openings_parser.add_argument("--limit", type=int, default=100)
    return parser


def _collect(settings, source: str | None, enqueue: bool) -> None:
    config = load_sources_config(settings.sources_config)
    if source:
        source_config = config.get(source)
        if source_config is None:
            raise ValueError(f"Unknown collection source: {source}")
        collectors = [get_collector(source, settings, source_config)]
    else:
        collectors = build_collectors(settings, config)

    if enqueue:
        for collector in collectors:
            enqueue_collect_job(settings, collector.name)
        print(json.dumps({"enqueued": len(collectors)}))
        return

    with session_scope(settings) as session:
        if source:
            results = {source: collect_source(session, collectors[0], settings)}
        else:
            results = collect_all(session, collectors, settings)

    print(json.dumps({name: asdict(stats) for name, stats in results.items()}, indent=2))
    if any(stats.errors for stats in results.values()):
        raise SystemExit(1)


def _list_openings(settings, limit: int) -> None:
    with session_scope(settings) as session:
        openings = list_openings(session, limit=limit)
        result = [opening.model_dump(mode="json") for opening in openings]
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    settings = get_settings()

    if args.command == "collect":
        _collect(settings, args.source, args.enqueue)
    elif args.command == "tailor":
        opening_id = UUID(args.opening_id)
        with session_scope(settings) as session:
            pdf_path = tailor_resume(
                session,
                opening_id=opening_id,
                kb_path=settings.kb_path,
                out_dir=settings.artifacts_dir,
                llm=OpenRouterClient(
                    api_key=settings.openrouter_api_key,
                    model=settings.openrouter_tailoring_model,
                ),
            )
        print(pdf_path)
    elif args.command == "gmail-auth":
        run_gmail_auth(settings)
        print(f"Gmail authorization saved to {settings.gmail_token_file}")
    elif args.command == "list-openings":
        _list_openings(settings, args.limit)


if __name__ == "__main__":
    main()
