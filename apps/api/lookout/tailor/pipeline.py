import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlmodel import Session

from lookout.kb import (
    KnowledgeBase,
    KnowledgeBaseError,
    kb_to_prompt_text,
    load_identity,
    load_resume_content,
)
from lookout.llm import OpenRouterClient
from lookout.models import Opening
from lookout.openings import get_opening
from lookout.redaction import contains_pii, redact
from lookout.tailor.pdf import html_to_pdf
from lookout.tailor.prompts import build_tailor_prompt
from lookout.tailor.render import detect_language, render_resume_html
from lookout.tailor.schema import ResumeSelection
from lookout.tailor.validation import materialize_selection, validate_resume


class TailorError(Exception):
    pass


def tailor_resume(
    session: Session,
    *,
    opening_id: uuid.UUID,
    kb_path: Path,
    out_dir: Path,
    llm: OpenRouterClient,
) -> Path:
    opening: Opening | None = get_opening(session, opening_id)
    if opening is None:
        raise TailorError(f"Opening not found: {opening_id}")

    language = detect_language(f"{opening.title} {opening.description}")
    try:
        content = load_resume_content(kb_path, language=language)
        identity = load_identity(kb_path)
    except KnowledgeBaseError as exc:
        raise TailorError(f"Unable to load knowledge base: {exc}") from exc

    # The body allowlist never includes identity.md. Reject accidental personal
    # details in professional facts instead of silently rendering placeholders.
    kb_text = kb_to_prompt_text(content)
    if contains_pii(kb_text, identity):
        raise TailorError("Personal data found in resume body; keep it only in identity.md")
    system, user = build_tailor_prompt(opening=opening, kb_text=kb_text, language=language)
    system = redact(system, identity)
    user = redact(user, identity)
    if contains_pii(system + user, identity):
        raise TailorError("PII remains in the LLM payload after redaction")

    response = llm.complete_json(system=system, user=user)

    try:
        selection = ResumeSelection.model_validate(response)
        resume = materialize_selection(selection, content, language=language)
    except (ValidationError, ValueError):
        raise TailorError("OpenRouter returned an invalid fact selection") from None

    violations = validate_resume(resume, content)
    if violations:
        raise TailorError("Tailored resume contains unsupported facts: " + "; ".join(violations))

    kb = KnowledgeBase(identity=identity, **vars(content))
    html = render_resume_html(resume, kb)
    return html_to_pdf(html, out_dir / f"{opening_id}.pdf")
