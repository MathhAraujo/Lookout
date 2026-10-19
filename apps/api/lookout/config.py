from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg://lookout:lookout@postgres:5432/lookout"
    openrouter_api_key: str = ""
    openrouter_tailoring_model: str = "anthropic/claude-3.5-haiku"
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    gmail_credentials_file: Path = Path("data/gmail_credentials.json")
    gmail_token_file: Path = Path("data/gmail_token.json")
    gmail_label: str = "lookout/jobs"
    kb_path: Path = Path("data/kb")
    artifacts_dir: Path = Path("data/artifacts")
    sources_config: Path = Path("config/sources.yml")
    worker_poll_seconds: int = 5
    dedup_company_threshold: float = 90.0
    dedup_title_threshold: float = 90.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
