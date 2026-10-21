import socket
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlmodel import Session, select

from lookout.browser_sessions import BrowserSessionInUseError, BrowserSessionManager
from lookout.config import Settings
from lookout.db import utcnow
from lookout.models import ConnectorHealth
from lookout.secrets import SecretProvider, SecretProviderError

ConnectorStatus = Literal["healthy", "degraded", "unavailable"]
ConnectorPlatform = Literal["greenhouse", "lever", "email"]
_BROWSER_HEALTH_URLS = {
    "greenhouse": "https://boards.greenhouse.io/",
    "lever": "https://jobs.lever.co/",
}
_SAFE_HEALTH_DETAILS = {
    "smtp_configuration_missing",
    "smtp_secret_unavailable",
    "smtp_unavailable",
    "smtp_available",
    "browser_session_expired",
    "manual_verification_required",
    "browser_profile_in_use",
    "browser_session_unavailable",
    "browser_platform_unavailable",
    "browser_session_healthy",
    "health_check_failed",
}
_AUTH_URL_MARKERS = ("/login", "/signin", "/sign-in")
_AUTH_TEXT_MARKERS = (
    "login required",
    "please sign in",
    "please log in",
    "sign in to continue",
    "session expired",
)
_VERIFICATION_MARKERS = (
    "captcha",
    "two-factor",
    "two factor",
    "2fa",
    "verification code",
    "authenticator code",
)


@dataclass(frozen=True)
class ConnectorHealthSnapshot:
    connector: str
    status: ConnectorStatus
    detail: str
    last_success_at: datetime | None


def _snapshot(
    connector: str,
    status: ConnectorStatus,
    detail: str,
    *,
    last_success_at: datetime | None = None,
) -> ConnectorHealthSnapshot:
    return ConnectorHealthSnapshot(
        connector=connector,
        status=status,
        detail=detail,
        last_success_at=last_success_at,
    )


def _check_email_health(settings: Settings, secrets: SecretProvider) -> ConnectorHealthSnapshot:
    if not settings.smtp_host.strip() or not settings.smtp_from.strip():
        return _snapshot("email", "unavailable", "smtp_configuration_missing")

    try:
        password = secrets.get_secret(
            settings.smtp_password_secret_name,
            path=settings.infisical_secret_path,
        )
    except SecretProviderError:
        return _snapshot("email", "unavailable", "smtp_secret_unavailable")
    if not password:
        return _snapshot("email", "unavailable", "smtp_secret_unavailable")

    try:
        with socket.create_connection((settings.smtp_host, settings.smtp_port), timeout=5):
            pass
    except OSError:
        return _snapshot("email", "degraded", "smtp_unavailable")

    return _snapshot("email", "healthy", "smtp_available", last_success_at=utcnow())


def _check_browser_health(
    platform: Literal["greenhouse", "lever"],
    sessions: BrowserSessionManager,
) -> ConnectorHealthSnapshot:
    try:
        with sessions.open(platform, headless=True) as context:
            page = context.new_page()
            response = page.goto(
                _BROWSER_HEALTH_URLS[platform],
                wait_until="domcontentloaded",
                timeout=10_000,
            )
            page_url = page.url.casefold()
            page_text = page.locator("body").inner_text(timeout=3_000).casefold()
            if any(marker in page_text for marker in _VERIFICATION_MARKERS):
                return _snapshot(platform, "degraded", "manual_verification_required")
            if (
                any(marker in page_url for marker in _AUTH_URL_MARKERS)
                or any(marker in page_text for marker in _AUTH_TEXT_MARKERS)
                or (response is not None and response.status in {401, 403})
            ):
                return _snapshot(platform, "degraded", "browser_session_expired")
            if response is None or response.status >= 500:
                return _snapshot(platform, "unavailable", "browser_platform_unavailable")
            if response.status >= 400:
                return _snapshot(platform, "degraded", "browser_platform_unavailable")
            return _snapshot(
                platform, "healthy", "browser_session_healthy", last_success_at=utcnow()
            )
    except BrowserSessionInUseError:
        return _snapshot(platform, "degraded", "browser_profile_in_use")
    # Fail-closed: Playwright raises many exception types on this boundary; degrade the
    # snapshot instead of crashing the daily connectivity check.
    except Exception:  # noqa: BLE001
        return _snapshot(platform, "unavailable", "browser_session_unavailable")


def check_connector_health(
    platform: ConnectorPlatform,
    *,
    settings: Settings,
    secrets: SecretProvider,
    sessions: BrowserSessionManager,
) -> ConnectorHealthSnapshot:
    if platform == "email":
        return _check_email_health(settings, secrets)
    if platform not in _BROWSER_HEALTH_URLS:
        raise ValueError("unsupported connector")
    return _check_browser_health(platform, sessions)


def _safe_detail(detail: str) -> str:
    return detail if detail in _SAFE_HEALTH_DETAILS else "health_check_failed"


def save_connector_health(
    session: Session,
    snapshot: ConnectorHealthSnapshot,
    *,
    now: datetime | None = None,
) -> ConnectorHealth:
    if snapshot.status not in {"healthy", "degraded", "unavailable"}:
        raise ValueError("unsupported connector health status")
    checked_at = now or utcnow()
    health = session.exec(
        select(ConnectorHealth).where(ConnectorHealth.connector == snapshot.connector)
    ).first()

    if health is None:
        health = ConnectorHealth(
            connector=snapshot.connector,
            status=snapshot.status,
            checked_at=checked_at,
            last_success_at=(
                snapshot.last_success_at or checked_at if snapshot.status == "healthy" else None
            ),
            detail=_safe_detail(snapshot.detail),
        )
        session.add(health)
    else:
        health.status = snapshot.status
        health.checked_at = checked_at
        health.detail = _safe_detail(snapshot.detail)
        if snapshot.status == "healthy":
            health.last_success_at = snapshot.last_success_at or checked_at

    session.flush()
    return health
