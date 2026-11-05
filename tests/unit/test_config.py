from pathlib import Path

from lookout.config import Settings


def test_settings_accepts_shared_compose_environment_file():
    settings = Settings(_env_file=Path(".env.example"))
    assert settings.worker_poll_seconds == 5
    assert settings.dry_run is True
