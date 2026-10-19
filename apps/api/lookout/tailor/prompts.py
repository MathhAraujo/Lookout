from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lookout.models import Opening

_GUARDRAIL = (
    "Use ONLY facts present in the knowledge base below. Never invent employers, roles, dates, "
    "projects or skills. Every experience and project in your output must carry the exact kb_id "
    "from the knowledge base. Output JSON only."
)
_LANGUAGE_NAMES = {"en": "English", "pt-br": "Brazilian Portuguese"}


def build_tailor_prompt(
    *,
    opening: Opening,
    kb_text: str,
    language: str,
) -> tuple[str, str]:
    language_name = _LANGUAGE_NAMES.get(language.casefold(), language)
    system = f"{_GUARDRAIL}\n\nWrite the resume in {language_name}, following the job posting's language."
    user = (
        "Job posting:\n"
        f"Company: {opening.company}\n"
        f"Title: {opening.title}\n"
        f"Description:\n{opening.description}\n\n"
        f"Knowledge base:\n{kb_text}"
    )
    return system, user
