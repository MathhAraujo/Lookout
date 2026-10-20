from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lookout.models import Opening

_GUARDRAIL = (
    "Use ONLY facts present in the knowledge base below. Never invent employers, roles, dates, "
    "projects or skills. Every experience and project in your output must carry the exact kb_id "
    "from the knowledge base. Output JSON only."
)
_OUTPUT_SCHEMA = """Return one JSON object using exactly this structure, with no markdown or extra keys:
{
  "language": "en",
  "summary": "...",
  "experiences": [{"kb_id": "<exact experience id from the knowledge base>", "highlights": ["..."]}],
  "projects": [{"kb_id": "<exact project id from the knowledge base>", "highlights": ["..."]}],
  "skills": ["..."]
}
Use "pt-br" instead of "en" when the job posting is in Brazilian Portuguese. Use empty arrays when there are no supported facts. Skills must come from the knowledge base."""
_LANGUAGE_NAMES = {"en": "English", "pt-br": "Brazilian Portuguese"}


def build_tailor_prompt(
    *,
    opening: Opening,
    kb_text: str,
    language: str,
) -> tuple[str, str]:
    language_name = _LANGUAGE_NAMES.get(language.casefold(), language)
    system = (
        f"{_GUARDRAIL}\n\n{_OUTPUT_SCHEMA}\n\n"
        f"Write the resume in {language_name}, following the job posting's language."
    )
    user = (
        "Job posting:\n"
        f"Company: {opening.company}\n"
        f"Title: {opening.title}\n"
        f"Description:\n{opening.description}\n\n"
        f"Knowledge base:\n{kb_text}"
    )
    return system, user
