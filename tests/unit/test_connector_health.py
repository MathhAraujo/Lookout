from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from lookout.config import Settings
from lookout.connector_health import (
    ConnectorHealthSnapshot,
    check_connector_health,
    save_connector_health,
)
from lookout.models import ConnectorHealth
from lookout.secrets import SecretProviderError
from sqlmodel import select


class FakeSecrets:
    def __init__(self, value="fictional-smtp-password", error=None):
        self.value = value
        self.error = error
        self.calls = []

    def get_secret(self, name: str, *, path: str) -> str:
        self.calls.append((name, path))
        if self.error is not None:
            raise self.error
        return self.value


class FakePage:
    def __init__(self, *, url="https://boards.greenhouse.io/", body="Job board"):
        self.url = url
        self.body = body
        self.goto_calls = []

    def goto(self, url, *, wait_until, timeout):
        self.goto_calls.append((url, wait_until, timeout))
        return SimpleNamespace(status=200)

    def locator(self, selector):
        assert selector == "body"
        return self

    def inner_text(self, *, timeout):
        return self.body


class FakeBrowserContext:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page


class FakeSessions:
    def __init__(self, page):
        self.page = page
        self.calls = []

    @contextmanager
    def open(self, platform, *, headless):
        self.calls.append((platform, headless))
        yield FakeBrowserContext(self.page)


def smtp_settings(**overrides) -> Settings:
    values = {
        "smtp_host": "smtp.example.test",
        "smtp_port": 2525,
        "smtp_from": "lookout@example.test",
        "smtp_password_secret_name": "SMTP_PASSWORD",
        "infisical_secret_path": "/application",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_email_health_checks_secret_and_smtp_connectivity(monkeypatch):
    calls = []

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    def create_connection(address, *, timeout):
        calls.append((address, timeout))
        return FakeSocket()

    monkeypatch.setattr("lookout.connector_health.socket.create_connection", create_connection)
    secrets = FakeSecrets()

    snapshot = check_connector_health(
        "email",
        settings=smtp_settings(),
        secrets=secrets,
        sessions=FakeSessions(FakePage()),
    )

    assert snapshot.status == "healthy"
    assert snapshot.detail == "smtp_available"
    assert snapshot.last_success_at is not None
    assert secrets.calls == [("SMTP_PASSWORD", "/application")]
    assert calls == [(('smtp.example.test', 2525), 5)]
    assert "fictional-smtp-password" not in str(snapshot)


def test_email_health_sanitizes_missing_secret_failure():
    secret = "fictional-secret-value-must-not-leak"
    snapshot = check_connector_health(
        "email",
        settings=smtp_settings(),
        secrets=FakeSecrets(error=SecretProviderError(secret)),
        sessions=FakeSessions(FakePage()),
    )

    assert snapshot.status == "unavailable"
    assert snapshot.detail == "smtp_secret_unavailable"
    assert secret not in str(snapshot)


def test_browser_health_downgrades_expired_session_without_logging_page_content():
    private_text = "Candidate Example is signed out"
    page = FakePage(url="https://boards.greenhouse.io/login", body=private_text)
    sessions = FakeSessions(page)

    snapshot = check_connector_health(
        "greenhouse",
        settings=Settings(_env_file=None),
        secrets=FakeSecrets(),
        sessions=sessions,
    )

    assert snapshot.status == "degraded"
    assert snapshot.detail == "browser_session_expired"
    assert sessions.calls == [("greenhouse", True)]
    assert private_text not in str(snapshot)


def test_browser_health_surfaces_captcha_or_two_factor_as_manual_verification():
    page = FakePage(body="Please enter your verification code to continue.")

    snapshot = check_connector_health(
        "lever",
        settings=Settings(_env_file=None),
        secrets=FakeSecrets(),
        sessions=FakeSessions(page),
    )

    assert snapshot.status == "degraded"
    assert snapshot.detail == "manual_verification_required"


def test_connector_health_upsert_persists_safe_detail_and_last_success(session):
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    healthy = save_connector_health(
        session,
        ConnectorHealthSnapshot(
            connector="email",
            status="healthy",
            detail="smtp_available",
            last_success_at=now,
        ),
        now=now,
    )
    fake_secret = "fictional-secret-value-must-not-persist"
    failed = save_connector_health(
        session,
        ConnectorHealthSnapshot(
            connector="email",
            status="degraded",
            detail=f"SMTP failed with password {fake_secret}",
            last_success_at=None,
        ),
        now=now,
    )
    records = session.exec(select(ConnectorHealth)).all()

    assert failed.id == healthy.id
    assert failed.status == "degraded"
    assert failed.detail == "health_check_failed"
    assert failed.last_success_at == now
    assert fake_secret not in str(records)
    assert len(records) == 1
