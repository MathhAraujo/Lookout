"""EmailApplier tests: explicit target only, dry-run never sends, SMTP via Infisical password."""

from email import message_from_bytes
from email.header import decode_header, make_header

from _helpers import make_application, make_opening
from lookout.appliers import EmailApplier
from lookout.config import Settings
from lookout.secrets import SecretProviderError


class _FakeSecrets:
    def __init__(self, *, value: str | None = "fake-smtp-password", error: Exception | None = None):
        self.calls = []
        self.value = value
        self.error = error

    def get_secret(self, name, *, path):
        self.calls.append((name, path))
        if self.error is not None:
            raise self.error
        return self.value


class _RecordingSMTP:
    def __init__(self, host, port, log) -> None:
        self.host = host
        self.port = port
        self.log = log
        self.sendmail_calls = []
        log.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def sendmail(self, *, from_addr, to_addrs, msg):
        self.sendmail_calls.append((from_addr, tuple(to_addrs), msg))


class _FailingSMTP:
    def __init__(self, host, port, log) -> None:
        log.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def sendmail(self, **kwargs):
        raise RuntimeError("connection dropped")


def make_settings() -> Settings:
    return Settings(
        smtp_host="smtp.fictional.test",
        smtp_port=2525,
        smtp_from="ada@fictional.test",
        infisical_url="http://infisical.test",
        infisical_client_id="id",
        infisical_client_secret="secret",
        infisical_project_id="project",
        infisical_environment="dev",
        infisical_secret_path="/application",
        smtp_password_secret_name="SMTP_PASSWORD",
    )


def _resume(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 fictional resume\n")
    return resume


def _targeted_opening():
    return make_opening(
        "https://boards.example.test/j/9001",
        application_email="careers@fictional.test",
    )


def test_dry_run_never_connects(tmp_path):
    secrets = _FakeSecrets()
    connections = []
    applier = EmailApplier(
        make_settings(),
        secrets,
        smtp_factory=lambda host, port: _RecordingSMTP(host, port, connections),
    )

    result = applier.submit(
        make_application(),
        _targeted_opening(),
        resume_path=_resume(tmp_path),
        answers=[],
        dry_run=True,
        auto_submit_enabled=False,
    )

    assert (result.status, result.detail) == ("dry_run", "dry_run_email_prepared")
    assert connections == []
    assert secrets.calls == []


def test_dry_run_missing_resume_refuses(tmp_path):
    secrets = _FakeSecrets()
    connections = []
    applier = EmailApplier(
        make_settings(),
        secrets,
        smtp_factory=lambda host, port: _RecordingSMTP(host, port, connections),
    )

    result = applier.submit(
        make_application(),
        _targeted_opening(),
        resume_path=tmp_path / "absent-resume.pdf",
        answers=[],
        dry_run=True,
        auto_submit_enabled=False,
    )

    assert (result.status, result.detail) == ("manual_assist", "resume_artifact_missing")
    assert connections == []
    assert secrets.calls == []


def test_submit_sends_once_to_the_explicit_target_with_pdf_attachment(tmp_path):
    secrets = _FakeSecrets()
    connections = []
    applier = EmailApplier(
        make_settings(),
        secrets,
        smtp_factory=lambda host, port: _RecordingSMTP(host, port, connections),
    )

    result = applier.submit(
        make_application(),
        _targeted_opening(),
        resume_path=_resume(tmp_path),
        answers=[],
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert (result.status, result.detail) == ("submitted", "email_sent")
    assert secrets.calls == [("SMTP_PASSWORD", "/application")]
    assert len(connections) == 1
    from_addr, to_addrs, msg = connections[0].sendmail_calls[0]
    assert connections[0].host == "smtp.fictional.test"
    assert connections[0].port == 2525
    assert from_addr == "ada@fictional.test"
    assert to_addrs == ("careers@fictional.test",)
    parsed = message_from_bytes(msg)
    subject = str(make_header(decode_header(parsed["Subject"])))
    assert subject == "Application — Senior Backend Engineer"
    assert parsed["From"] == "ada@fictional.test"
    assert parsed["To"] == "careers@fictional.test"
    content_types = {part.get_content_type() for part in parsed.walk()}
    assert {"text/plain", "application/pdf"} <= content_types


def test_message_body_follows_the_detected_posting_language(tmp_path):
    secrets = _FakeSecrets()
    connections = []
    applier = EmailApplier(
        make_settings(),
        secrets,
        smtp_factory=lambda host, port: _RecordingSMTP(host, port, connections),
    )
    portuguese_opening = make_opening(
        "https://boards.example.test/j/9002",
        application_email="vagas@fictional.test",
        description=(
            "Escritorio com times de trabalho remoto. A vaga e sobre construir sistemas "
            "de plataforma. Sobre a empresa: empresa fictional de tecnologia."
        ),
    )

    applier.submit(
        make_application(),
        portuguese_opening,
        resume_path=_resume(tmp_path),
        answers=[],
        dry_run=False,
        auto_submit_enabled=True,
    )

    parsed = message_from_bytes(connections[0].sendmail_calls[0][2])
    body = next(
        part.get_payload() for part in parsed.walk() if part.get_content_type() == "text/plain"
    )
    assert "vaga" in body
    assert "attached my resume" not in body


def test_missing_email_target_degrades_before_smtp(tmp_path):
    secrets = _FakeSecrets()
    connections = []
    applier = EmailApplier(
        make_settings(),
        secrets,
        smtp_factory=lambda host, port: _RecordingSMTP(host, port, connections),
    )
    opening = make_opening("https://boards.example.test/j/9001")

    result = applier.submit(
        make_application(),
        opening,
        resume_path=_resume(tmp_path),
        answers=[],
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert (result.status, result.detail) == ("manual_assist", "application_email_missing")
    assert connections == []
    assert secrets.calls == []


def test_missing_smtp_configuration_checks_before_secret_retrieval(tmp_path):
    secrets = _FakeSecrets()
    connections = []
    settings = make_settings()
    settings.smtp_host = ""
    applier = EmailApplier(
        settings,
        secrets,
        smtp_factory=lambda host, port: _RecordingSMTP(host, port, connections),
    )
    resume = _resume(tmp_path)
    opening = _targeted_opening()

    result = applier.submit(
        make_application(),
        opening,
        resume_path=resume,
        answers=[],
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert (result.status, result.detail) == ("manual_assist", "smtp_configuration_missing")
    assert connections == []
    assert secrets.calls == []


def test_missing_smtp_secret_degrades_to_manual_assist(tmp_path):
    secrets = _FakeSecrets(error=SecretProviderError("not available"))
    connections = []
    applier = EmailApplier(
        make_settings(),
        secrets,
        smtp_factory=lambda host, port: _RecordingSMTP(host, port, connections),
    )
    opening = _targeted_opening()

    result = applier.submit(
        make_application(),
        opening,
        resume_path=_resume(tmp_path),
        answers=[],
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert (result.status, result.detail) == ("manual_assist", "smtp_password_unavailable")
    assert connections == []
    assert secrets.calls == [("SMTP_PASSWORD", "/application")]


def test_smtp_failure_degrades_to_manual_assist(tmp_path):
    secrets = _FakeSecrets()
    connections = []
    applier = EmailApplier(
        make_settings(),
        secrets,
        smtp_factory=lambda host, port: _FailingSMTP(host, port, connections),
    )
    opening = _targeted_opening()

    result = applier.submit(
        make_application(),
        opening,
        resume_path=_resume(tmp_path),
        answers=[],
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert (result.status, result.detail) == ("manual_assist", "smtp_send_failed")


def test_guard_blocks_real_submission_before_smtp(tmp_path):
    secrets = _FakeSecrets()
    connections = []
    applier = EmailApplier(
        make_settings(),
        secrets,
        smtp_factory=lambda host, port: _RecordingSMTP(host, port, connections),
    )
    opening = _targeted_opening()

    flags_off = applier.submit(
        make_application(),
        opening,
        resume_path=_resume(tmp_path),
        answers=[],
        dry_run=False,
        auto_submit_enabled=False,
    )
    review_lane = applier.submit(
        make_application(lane="review"),
        opening,
        resume_path=_resume(tmp_path),
        answers=[],
        dry_run=False,
        auto_submit_enabled=True,
    )

    assert (flags_off.status, flags_off.detail) == ("manual_assist", "auto_submit_disabled")
    assert (review_lane.status, review_lane.detail) == ("manual_assist", "lane_not_auto_apply")
    assert connections == []
    assert secrets.calls == []


def test_inspect_returns_an_empty_form():
    secrets = _FakeSecrets()
    applier = EmailApplier(make_settings(), secrets, smtp_factory=lambda host, port: None)
    opening = _targeted_opening()

    form = applier.inspect(opening, resume_path=None)

    assert form.fields == []
    assert secrets.calls == []
