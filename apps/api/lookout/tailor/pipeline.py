import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlmodel import Session

from lookout.kb import KnowledgeBaseError, kb_to_prompt_text, load_knowledge_base
from lookout.llm import OpenRouterClient
from lookout.models import Opening
from lookout.openings import get_opening
from lookout.redaction import contains_pii, redact
from lookout.tailor.pdf import html_to_pdf
from lookout.tailor.prompts import build_tailor_prompt
from lookout.tailor.render import detect_language, render_resume_html
from lookout.tailor.schema import TailoredResume
from lookout.tailor.validation import validate_resume


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

    try:
        kb = load_knowledge_base(kb_path)
    except KnowledgeBaseError as exc:
        raise TailorError(f"Unable to load knowledge base: {exc}") from exc

    kb_text = redact(kb_to_prompt_text(kb), kb.identity)
    if contains_pii(kb_text, kb.identity):
        raise TailorError("PII remains in the knowledge base prompt after redaction")

    language = detect_language(opening.description)
    system, user = build_tailor_prompt(opening=opening, kb_text=kb_text, language=language)
    system = redact(system, kb.identity)
    user = redact(user, kb.identity)
    if contains_pii(system + user, kb.identity):
        raise TailorError("PII remains in the LLM payload after redaction")

    response = llm.complete_json(system=system, user=user)

    try:
        resume = TailoredResume.model_validate(response)
    except ValidationError as exc:
        raise TailorError(f"OpenRouter returned an invalid tailored resume: {exc}") from exc

    violations = validate_resume(resume, kb)
    if violations:
        raise TailorError("Tailored resume contains unsupported facts: " + "; ".join(violations))

    html = render_resume_html(resume, kb)
    return html_to_pdf(html, out_dir / f"{opening_id}.pdf")
