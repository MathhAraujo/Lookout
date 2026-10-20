from lookout.kb import KnowledgeBase
from lookout.tailor.schema import TailoredResume


def _normalized_fact(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate_resume(resume: TailoredResume, kb: KnowledgeBase) -> list[str]:
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
