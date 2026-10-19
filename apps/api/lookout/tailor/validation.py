from lookout.kb import KnowledgeBase
from lookout.tailor.schema import TailoredResume


def validate_resume(resume: TailoredResume, kb: KnowledgeBase) -> list[str]:
    violations = []
    experience_ids = {experience.id for experience in kb.experiences}
    project_ids = {project.id for project in kb.projects}

    for experience in resume.experiences:
        if experience.kb_id not in experience_ids:
            violations.append(f"Unknown experience kb_id: {experience.kb_id}")

    for project in resume.projects:
        if project.kb_id not in project_ids:
            violations.append(f"Unknown project kb_id: {project.kb_id}")

    known_skills = {skill.casefold() for skill in kb.skills}
    for skill in resume.skills:
        if skill.strip().casefold() not in known_skills:
            violations.append(f"Unknown skill: {skill}")

    return violations
