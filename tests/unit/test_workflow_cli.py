"""Operational CLI commands exercise the same durable controls as the API."""

import json
from datetime import timedelta

from lookout.cli import main
from lookout.config import Settings
from lookout.db import utcnow
from lookout.models import Application, Job
from sqlmodel import select


def run_cli(monkeypatch, engine, *arguments):
    monkeypatch.setattr("sys.argv", ["lookout", *map(str, arguments)])
    monkeypatch.setattr(
        "lookout.cli.get_settings",
        lambda: Settings(
            _env_file=None, database_url=engine.url.render_as_string(hide_password=False)
        ),
    )
    main()


def test_match_backfill_is_repeatable(monkeypatch, engine, session, opening_fixture, capsys):
    session.commit()
    run_cli(monkeypatch, engine, "match", "--backfill")
    assert json.loads(capsys.readouterr().out)["enqueued"] == 1
    run_cli(monkeypatch, engine, "match", "--backfill")
    assert json.loads(capsys.readouterr().out)["enqueued"] == 0


def test_cli_list_and_approve_review(monkeypatch, engine, session, opening_fixture, capsys):
    application = Application(
        opening_id=opening_fixture.id,
        lane="review",
        status="awaiting_review",
        review_expires_at=utcnow() + timedelta(days=7),
    )
    session.add(application)
    session.commit()
    application_id = application.id
    run_cli(monkeypatch, engine, "list-applications", "--lane", "review")
    assert json.loads(capsys.readouterr().out)[0]["opening"]["company"] == "Globex"
    run_cli(monkeypatch, engine, "approve", application_id)
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    session.expire_all()
    assert session.get(Application, application_id).lane == "auto_apply"
    assert session.exec(select(Job).where(Job.type == "apply")).one().payload == {
        "application_id": str(application_id)
    }
