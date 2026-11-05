from lookout.kb import ResumeContent
from lookout.tailor.schema import (
    ResumeSelection,
    TailoredExperience,
    TailoredProject,
    TailoredResume,
)


def _normalized_fact(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate_resume(resume: TailoredResume, kb: ResumeContent) -> list[str]:
    violations = []
    experiences_by_id = {experience.id: experience for experience in kb.experiences}
    projects_by_id = {project.id: project for project in kb.projects}

    known_summary_facts = [kb.summary, *kb.skills, *kb.languages, *kb.education]
    for experience in kb.experiences:
        known_summary_facts.extend(
            [
                experience.role,
                experience.company,
                experience.start,
                experience.end or "",
                experience.summary,
                *experience.highlights,
                *experience.tech,
            ]
        )
    for project in kb.projects:
        known_summary_facts.extend(
            [project.name, project.summary, *project.highlights, *project.tech]
        )

    allowed_summaries = {_normalized_fact(fact) for fact in known_summary_facts if fact.strip()}
    if _normalized_fact(resume.summary) not in allowed_summaries:
        violations.append("Unsupported summary: it must copy a knowledge-base fact verbatim")

    for experience in resume.experiences:
        source = experiences_by_id.get(experience.kb_id)
        if source is None:
            violations.append(f"Unknown experience kb_id: {experience.kb_id}")
            continue

        allowed_highlights = {_normalized_fact(fact) for fact in source.highlights}
        for highlight in experience.highlights:
            if _normalized_fact(highlight) not in allowed_highlights:
                violations.append(f"Unsupported experience highlight for kb_id: {experience.kb_id}")

    for project in resume.projects:
        source = projects_by_id.get(project.kb_id)
        if source is None:
            violations.append(f"Unknown project kb_id: {project.kb_id}")
            continue

        allowed_highlights = {_normalized_fact(fact) for fact in source.highlights}
        for highlight in project.highlights:
            if _normalized_fact(highlight) not in allowed_highlights:
                violations.append(f"Unsupported project highlight for kb_id: {project.kb_id}")

    known_skills = {skill.casefold() for skill in kb.skills}
    for skill in resume.skills:
        if skill.strip().casefold() not in known_skills:
            violations.append(f"Unknown skill: {skill}")

    return violations


def materialize_selection(
    selection: ResumeSelection, content: ResumeContent, *, language: str
) -> TailoredResume:
    if selection.language != language:
        raise ValueError("Selection language does not match the posting")

    def select_items(selected, source_items, model):
        source_by_id = {item.id: item for item in source_items}
        result, seen = [], set()
        for item in selected:
            source = source_by_id.get(item.kb_id)
            if source is None or item.kb_id in seen:
                raise ValueError("Unknown or repeated knowledge-base identifier")
            if len(item.highlights) != len(set(item.highlights)) or any(
                index >= len(source.highlights) for index in item.highlights
            ):
                raise ValueError("Invalid highlight selection")
            seen.add(item.kb_id)
            result.append(
                model(
                    kb_id=item.kb_id,
                    highlights=[source.highlights[index] for index in item.highlights],
                )
            )
        return result

    if len(selection.skills) != len(set(selection.skills)) or any(
        skill not in content.skills for skill in selection.skills
    ):
        raise ValueError("Invalid skill selection")
    return TailoredResume(
        language=language,
        summary=content.summary,
        experiences=select_items(selection.experiences, content.experiences, TailoredExperience),
        projects=select_items(selection.projects, content.projects, TailoredProject),
        skills=selection.skills,
    )
