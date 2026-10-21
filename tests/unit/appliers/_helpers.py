"""Reusable model builders for the applier tests."""

from uuid import uuid4

from lookout.models import Application, Opening
from lookout.screener import ResolvedAnswer


def base_url(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def make_opening(
    url: str,
    *,
    source: str = "greenhouse",
    application_email=None,
    description: str = "Build fictional platform systems.",
) -> Opening:
    return Opening(
        source=source,
        external_id="9001",
        company="Fictional Sciences",
        title="Senior Backend Engineer",
        url=url,
        description=description,
        dedup_key="dedup-9001",
        application_email=application_email,
    )


def make_application(**overrides) -> Application:
    fields = {
        "lane": "auto_apply",
        "status": "submitting",
        "opening_id": uuid4(),
    }
    fields.update(overrides)
    return Application(**fields)


def answered(key: str, answer: str) -> ResolvedAnswer:
    return ResolvedAnswer(key=key, answer=answer, source="fact", status="answered")


def greenhouse_answers() -> list[ResolvedAnswer]:
    return [
        answered("first_name", "Ada"),
        answered("last_name", "Lovelace"),
        answered("email", "ada@fictional.test"),
        answered("years_of_python_experience", "8"),
        answered("are_you_authorized_to_work_in_brazil", "Yes, authorized"),
    ]


def lever_answers() -> list[ResolvedAnswer]:
    return [
        answered("name", "Ada"),
        answered("email", "ada@fictional.test"),
        answered("experience_years", "8"),
        answered("authorized_to_work_in_brazil", "Yes, authorized"),
    ]
