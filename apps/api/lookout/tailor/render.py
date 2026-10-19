import re
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape

from lookout.kb import KnowledgeBase
from lookout.tailor.schema import TailoredResume

_TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "templates" / "resume"
_STOPWORDS = {
    "pt-br": {"de", "para", "com", "você", "experiência", "vaga", "trabalho"},
    "en": {"the", "and", "for", "with", "you", "experience", "job"},
}
_HEADINGS = {
    "en": {
        "summary": "Summary",
        "experience": "Experience",
        "projects": "Projects",
        "skills": "Skills",
        "education": "Education",
    },
    "pt-br": {
        "summary": "Resumo",
        "experience": "Experiência",
        "projects": "Projetos",
        "skills": "Competências",
        "education": "Formação",
    },
}


def detect_language(text: str) -> Literal["pt-br", "en"]:
    words = set(re.findall(r"\b\w+\b", text.casefold()))
    pt_score = len(words & _STOPWORDS["pt-br"])
    en_score = len(words & _STOPWORDS["en"])
    return "pt-br" if pt_score > en_score else "en"


def render_resume_html(resume: TailoredResume, kb: KnowledgeBase) -> str:
    experiences_by_id = {experience.id: experience for experience in kb.experiences}
    projects_by_id = {project.id: project for project in kb.projects}

    experiences = []
    for tailored in resume.experiences:
        source = experiences_by_id.get(tailored.kb_id)
        if source is None:
            raise ValueError(f"Unknown experience kb_id: {tailored.kb_id}")
        experiences.append(
            {
                "company": source.company,
                "role": source.role,
                "start": source.start,
                "end": source.end,
                "summary": source.summary,
                "highlights": tailored.highlights,
                "tech": source.tech,
            }
        )

    projects = []
    for tailored in resume.projects:
        source = projects_by_id.get(tailored.kb_id)
        if source is None:
            raise ValueError(f"Unknown project kb_id: {tailored.kb_id}")
        projects.append(
            {
                "name": source.name,
                "summary": source.summary,
                "highlights": tailored.highlights,
                "tech": source.tech,
            }
        )

    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("base.html")
    css = (_TEMPLATE_DIR / "resume.css").read_text(encoding="utf-8")
    return template.render(
        resume=resume,
        identity=kb.identity,
        experiences=experiences,
        projects=projects,
        education=kb.education,
        headings=_HEADINGS[resume.language],
        css=css,
    )
