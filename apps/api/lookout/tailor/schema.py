from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class TailoredExperience(BaseModel):
    kb_id: str
    highlights: list[str]


class TailoredProject(BaseModel):
    kb_id: str
    highlights: list[str]


class TailoredResume(BaseModel):
    language: Literal["pt-br", "en"]
    summary: str
    experiences: list[TailoredExperience]
    projects: list[TailoredProject]
    skills: list[str]


class SelectedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kb_id: str
    highlights: list[Annotated[int, Field(strict=True, ge=0)]]


class ResumeSelection(BaseModel):
    """The model can choose approved facts, never author the header or body text."""

    model_config = ConfigDict(extra="forbid")

    language: Literal["pt-br", "en"]
    experiences: list[SelectedItem]
    projects: list[SelectedItem]
    skills: list[str]
