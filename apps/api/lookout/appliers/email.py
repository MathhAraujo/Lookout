"""Explicit-email application adapter using SMTP and the Infisical SMTP password."""

import re
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from lookout.appliers.base import ApplicationForm, ApplyResult, submission_guard
from lookout.config import Settings
from lookout.normalize import normalize_text
from lookout.secrets import SecretProviderError

_PT_STOPWORDS = frozenset(
    {
        "de",
        "da",
        "do",
        "dos",
        "das",
        "para",
        "com",
        "sobre",
        "empresa",
        "vaga",
        "vagas",
        "trabalho",
        "times",
        "escritorio",
        "remoto",
    }
)
_EN_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "you",
        "will",
        "our",
        "team",
        "about",
        "company",
        "role",
        "work",
        "build",
        "remote",
    }
)
_TARGET_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def detect_description_language(description: str) -> str:
    """Return "pt" or "en" using deterministic stopword counts (English default)."""

    tokens = normalize_text(description).split()
    pt_hits = sum(1 for token in tokens if token in _PT_STOPWORDS)
    en_hits = sum(1 for token in tokens if token in _EN_STOPWORDS)
    return "pt" if pt_hits > en_hits else "en"


def _body_text(opening: Any, language: str) -> str:
    if language == "pt":
        return f"Ola,\n\nSegue em anexo meu curriculo para a vaga de {opening.title}.\n\nAtenciosamente."
    return f"Hello,\n\nPlease find attached my resume for the {opening.title} opening.\n\nBest regards."


class EmailApplier:
    """Sends a single application email to the explicit opening target only."""

    def __init__(
        self,
        settings: Settings,
        secrets: Any,
        *,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
    ) -> None:
        self._settings = settings
        self._secrets = secrets
        self._smtp_factory = smtp_factory

    def inspect(self, opening: Any, *, resume_path: Path) -> ApplicationForm:
        """Email applications carry no screenable form fields."""

        return ApplicationForm(fields=[])

    def submit(
        self,
        application: Any,
        opening: Any,
        *,
        resume_path: Path,
        answers: list,
        dry_run: bool,
        auto_submit_enabled: bool,
    ) -> ApplyResult:
        guard = submission_guard(
            application, dry_run=dry_run, auto_submit_enabled=auto_submit_enabled
        )
        if guard is not None:
            return guard
        if not Path(resume_path).is_file():
            return ApplyResult("manual_assist", "resume_artifact_missing")
        if dry_run:
            return ApplyResult("dry_run", "dry_run_email_prepared")

        target = (opening.application_email or "").strip()
        if not target or not _TARGET_PATTERN.fullmatch(target):
            return ApplyResult("manual_assist", "application_email_missing")
        if not self._settings.smtp_host.strip() or not self._settings.smtp_from.strip():
            return ApplyResult("manual_assist", "smtp_configuration_missing")
        try:
            password = self._secrets.get_secret(
                self._settings.smtp_password_secret_name,
                path=self._settings.infisical_secret_path,
            )
        except SecretProviderError:
            return ApplyResult("manual_assist", "smtp_password_unavailable")
        if not isinstance(password, str) or not password:
            return ApplyResult("manual_assist", "smtp_password_unavailable")

        message = self._build_message(opening, resume_path)
        try:
            with self._smtp_factory(self._settings.smtp_host, self._settings.smtp_port) as smtp:
                smtp.sendmail(
                    from_addr=self._settings.smtp_from,
                    to_addrs=[target],
                    msg=message.as_bytes(),
                )
        except Exception:  # noqa: BLE001 - SMTP failures must degrade, never crash the worker
            return ApplyResult("manual_assist", "smtp_send_failed")
        return ApplyResult("submitted", "email_sent")

    def _build_message(self, opening: Any, resume_path: Path) -> EmailMessage:
        language = detect_description_language(opening.description or "")
        message = EmailMessage()
        message["From"] = self._settings.smtp_from
        message["To"] = (opening.application_email or "").strip()
        message["Subject"] = f"Application — {opening.title}"
        message.set_content(_body_text(opening, language))
        data = Path(resume_path).read_bytes()
        message.add_attachment(data, maintype="application", subtype="pdf", filename="resume.pdf")
        return message
