from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Seniority = Literal["intern", "junior", "mid", "senior", "staff", "principal"]


class MatchProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ideal_job: str = Field(min_length=1)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    allowed_languages: list[str] = Field(default_factory=list)
    allowed_locations: list[str] = Field(default_factory=list)
    allowed_work_modes: list[str] = Field(default_factory=list)
    minimum_seniority: Seniority | None = None
    minimum_salary: float | None = Field(default=None, ge=0)
    salary_currency: str | None = None

    @field_validator(
        "include_keywords",
        "exclude_keywords",
        "allowed_languages",
        "allowed_locations",
        "allowed_work_modes",
        mode="before",
    )
    @classmethod
    def normalize_list_values(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return [item.strip() if isinstance(item, str) else item for item in value]
        return value

    @field_validator("salary_currency")
    @classmethod
    def normalize_salary_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class MatchProfileError(Exception):
    """Raised when the local match profile is missing or invalid."""


def load_match_profile(path: Path) -> MatchProfile:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise MatchProfileError("invalid match profile: expected a YAML mapping")
        return MatchProfile.model_validate(data)
    except MatchProfileError:
        raise
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError):
        raise MatchProfileError("invalid match profile") from None
