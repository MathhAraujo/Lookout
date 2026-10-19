from dataclasses import dataclass
from pathlib import Path

import frontmatter
import yaml


@dataclass(frozen=True)
class PiiProfile:
    full_name: str
    cpf: str
    phone: str
    address: str
    email: str


@dataclass
class Experience:
    id: str
    company: str
    role: str
    start: str
    end: str | None
    summary: str
    highlights: list[str]
    tech: list[str]


@dataclass
class Project:
    id: str
    name: str
    summary: str
    highlights: list[str]
    tech: list[str]


@dataclass
class KnowledgeBase:
    identity: PiiProfile
    summary: str
    experiences: list[Experience]
    projects: list[Project]
    skills: list[str]
    languages: list[str]
    education: list[str]


class KnowledgeBaseError(Exception):
    pass


def _required_string(metadata: dict, key: str, source: Path) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeBaseError(f"Missing required '{key}' value in {source}")
    return value.strip()


def _string_list(metadata: dict, key: str, source: Path) -> list[str]:
    values = metadata.get(key, [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise KnowledgeBaseError(f"Expected '{key}' to be a list of strings in {source}")
    return [value.strip() for value in values if value.strip()]


def _load_document(path: Path):
    try:
        return frontmatter.load(path)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise KnowledgeBaseError(f"Unable to load knowledge base file {path}: {exc}") from exc


def _missing_required_files(path: Path) -> list[str]:
    required = ["identity.md", "summary.md", "skills.md", "languages.md", "education.md"]
    missing = [name for name in required if not (path / name).is_file()]

    for folder in ("experiences", "projects"):
        entries = sorted((path / folder).glob("*.md")) if (path / folder).is_dir() else []
        if not entries:
            missing.append(f"{folder}/*.md")

    return missing


def _load_experiences(path: Path) -> list[Experience]:
    experiences = []
    for file_path in sorted((path / "experiences").glob("*.md")):
        document = _load_document(file_path)
        metadata = document.metadata
        end = metadata.get("end")
        experiences.append(
            Experience(
                id=_required_string(metadata, "id", file_path),
                company=_required_string(metadata, "company", file_path),
                role=_required_string(metadata, "role", file_path),
                start=_required_string(metadata, "start", file_path),
                end=end.strip() if isinstance(end, str) and end.strip() else None,
                summary=document.content.strip(),
                highlights=_string_list(metadata, "highlights", file_path),
                tech=_string_list(metadata, "tech", file_path),
            )
        )
    return experiences


def _load_projects(path: Path) -> list[Project]:
    projects = []
    for file_path in sorted((path / "projects").glob("*.md")):
        document = _load_document(file_path)
        metadata = document.metadata
        projects.append(
            Project(
                id=_required_string(metadata, "id", file_path),
                name=_required_string(metadata, "name", file_path),
                summary=document.content.strip(),
                highlights=_string_list(metadata, "highlights", file_path),
                tech=_string_list(metadata, "tech", file_path),
            )
        )
    return projects


def _load_items(path: Path) -> list[str]:
    document = _load_document(path)
    return _string_list(document.metadata, "items", path)


def load_knowledge_base(path: Path) -> KnowledgeBase:
    missing = _missing_required_files(path)
    if missing:
        raise KnowledgeBaseError(
            f"Missing required knowledge base files in {path}: {', '.join(missing)}"
        )

    identity_document = _load_document(path / "identity.md")
    identity_metadata = identity_document.metadata
    identity = PiiProfile(
        full_name=_required_string(identity_metadata, "full_name", path / "identity.md"),
        cpf=_required_string(identity_metadata, "cpf", path / "identity.md"),
        phone=_required_string(identity_metadata, "phone", path / "identity.md"),
        address=_required_string(identity_metadata, "address", path / "identity.md"),
        email=_required_string(identity_metadata, "email", path / "identity.md"),
    )

    return KnowledgeBase(
        identity=identity,
        summary=_load_document(path / "summary.md").content.strip(),
        experiences=_load_experiences(path),
        projects=_load_projects(path),
        skills=_load_items(path / "skills.md"),
        languages=_load_items(path / "languages.md"),
        education=_load_items(path / "education.md"),
    )


def kb_to_prompt_text(kb: KnowledgeBase) -> str:
    lines = ["Summary:", kb.summary, "", "Experiences:"]

    for experience in kb.experiences:
        dates = f"{experience.start}–{experience.end or 'Present'}"
        lines.append(f"[{experience.id}] {experience.role} at {experience.company} ({dates})")
        if experience.summary:
            lines.append(experience.summary)
        lines.extend(f"- {highlight}" for highlight in experience.highlights)
        if experience.tech:
            lines.append(f"Technology: {', '.join(experience.tech)}")

    lines.extend(["", "Projects:"])
    for project in kb.projects:
        lines.append(f"[{project.id}] {project.name}")
        if project.summary:
            lines.append(project.summary)
        lines.extend(f"- {highlight}" for highlight in project.highlights)
        if project.tech:
            lines.append(f"Technology: {', '.join(project.tech)}")

    lines.extend(
        [
            "",
            f"Skills: {', '.join(kb.skills)}",
            f"Languages: {', '.join(kb.languages)}",
            f"Education: {', '.join(kb.education)}",
        ]
    )
    return "\n".join(lines)
