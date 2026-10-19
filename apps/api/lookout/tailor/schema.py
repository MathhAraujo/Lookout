from typing import Literal

from pydantic import BaseModel


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
