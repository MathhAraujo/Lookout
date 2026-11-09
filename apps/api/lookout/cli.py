import argparse
import json
from dataclasses import asdict
from uuid import UUID

from lookout.applications import application_details, list_applications
from lookout.browser_sessions import BrowserSessionError, BrowserSessionManager
from lookout.collectors.linkedin_email import run_gmail_auth
from lookout.collectors.registry import build_collectors, get_collector, load_sources_config
from lookout.config import get_settings
from lookout.connector_health import refresh_connector_health
from lookout.db import session_scope
from lookout.ingest import collect_all, collect_source
from lookout.llm import OpenRouterClient
from lookout.openings import list_openings
from lookout.routing import InvalidReviewTransition, ReviewApplicationNotFoundError
from lookout.tailor.pipeline import tailor_resume
from lookout.worker import enqueue_collect_job
from lookout.workflow import enqueue_backfill, review_application


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

    applications_parser = commands.add_parser(
        "list-applications", help="List decisions and source links"
    )
    applications_parser.add_argument(
        "--lane", choices=["auto_apply", "review", "manual_assist", "rejected"]
    )
    applications_parser.add_argument("--status")
    applications_parser.add_argument("--limit", type=int, default=100)
    applications_parser.add_argument("--offset", type=int, default=0)
    for action in ("approve", "decline"):
        action_parser = commands.add_parser(action, help=f"{action.capitalize()} a waiting review")
        action_parser.add_argument("application_id", type=UUID)
    match_parser = commands.add_parser(
        "match", help="Enqueue matching for openings without a decision"
    )
    match_parser.add_argument(
        "--backfill", action="store_true", help="Include existing unprocessed openings (default)"
    )
    auth_parser = commands.add_parser(
        "browser-auth", help="Manually initialize a persistent browser session"
    )
    auth_parser.add_argument("platform", choices=["greenhouse", "lever"])
    commands.add_parser(
        "check-connectors", help="Refresh connector health without submitting applications"
    )
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

    print(
        json.dumps({name: asdict(stats) for name, stats in results.items()}, indent=2, default=str)
    )
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
        with (
            OpenRouterClient(
                api_key=settings.openrouter_api_key,
                model=settings.openrouter_tailoring_model,
            ) as llm,
            session_scope(settings) as session,
        ):
            pdf_path = tailor_resume(
                session,
                opening_id=opening_id,
                kb_path=settings.kb_path,
                out_dir=settings.artifacts_dir,
                llm=llm,
            )
        print(pdf_path)
    elif args.command == "gmail-auth":
        run_gmail_auth(settings)
        print(f"Gmail authorization saved to {settings.gmail_token_file}")
    elif args.command == "list-openings":
        _list_openings(settings, args.limit)
    elif args.command == "list-applications":
        with session_scope(settings) as session:
            result = [
                application_details(session, application)
                for application in list_applications(
                    session,
                    lane=args.lane,
                    status=args.status,
                    limit=args.limit,
                    offset=args.offset,
                )
            ]
        print(json.dumps(result, indent=2))
    elif args.command in {"approve", "decline"}:
        try:
            with session_scope(settings) as session:
                application = review_application(
                    session, args.application_id, approve=args.command == "approve"
                )
                result = application_details(session, application)
        except ReviewApplicationNotFoundError:
            parser.exit(1, "Application not found\n")
        except InvalidReviewTransition:
            parser.exit(1, "Application is not eligible for this review action\n")
        print(json.dumps(result, indent=2))
    elif args.command == "match":
        with session_scope(settings) as session:
            count = enqueue_backfill(session)
        print(json.dumps({"enqueued": count}))
    elif args.command == "check-connectors":
        with session_scope(settings) as session:
            result = [
                item.model_dump(mode="json") for item in refresh_connector_health(session, settings)
            ]
        print(json.dumps(result, indent=2))
    elif args.command == "browser-auth":
        try:
            with BrowserSessionManager(settings.browser_profiles_path).open(
                args.platform, headless=False
            ) as context:
                page = context.new_page()
                page.goto(
                    "https://boards.greenhouse.io/"
                    if args.platform == "greenhouse"
                    else "https://jobs.lever.co/"
                )
                input(
                    "Complete login manually in the browser, then press Enter to save the session: "
                )
        except (BrowserSessionError, EOFError):
            parser.exit(
                1, "Browser authentication requires an interactive terminal and a local display\n"
            )


if __name__ == "__main__":
    main()
