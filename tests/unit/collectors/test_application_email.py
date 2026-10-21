"""Explicit application-email extraction for Greenhouse and Lever collectors."""

from lookout.collectors.greenhouse import parse_greenhouse
from lookout.collectors.lever import parse_lever


def _greenhouse_payload(content: str, apply_email=None) -> dict:
    item = {
        "id": 9001,
        "title": "Senior Backend Engineer",
        "absolute_url": "https://boards.example.test/jobs/9001",
        "location": {"name": "Remote"},
        "updated_at": "2026-10-01T00:00:00Z",
        "content": content,
    }
    if apply_email is not None:
        item["applyEmail"] = apply_email
    return {"jobs": [item]}


def _lever_payload(content: str) -> list[dict]:
    return [
        {
            "id": "9001",
            "text": "Senior Backend Engineer",
            "hostedUrl": "https://jobs.example.test/p/9001",
            "createdAt": 1790000000000,
            "descriptionPlain": "Build fictional platform systems.",
            "content": content,
        }
    ]


def test_greenhouse_extracts_the_explicit_apply_mailto_anchor():
    payload = _greenhouse_payload(
        "<p>Build fictional systems.</p>"
        '<a href="mailto:apply@fictional.test?subject=Application">Apply to this role</a>'
    )

    parsed = parse_greenhouse(payload, "Fictional Sciences")

    assert parsed[0].application_email == "apply@fictional.test"


def test_greenhouse_prefers_the_explicit_apply_email_field():
    payload = _greenhouse_payload(
        "<p>Build fictional systems.</p>",
        apply_email="hiring@fictional.test",
    )

    parsed = parse_greenhouse(payload, "Fictional Sciences")

    assert parsed[0].application_email == "hiring@fictional.test"


def test_greenhouse_ignores_non_apply_mailto_contacts():
    payload = _greenhouse_payload('<a href="mailto:press@fictional.test">Our press team</a>')

    parsed = parse_greenhouse(payload, "Fictional Sciences")

    assert parsed[0].application_email is None


def test_greenhouse_refuses_ambiguous_apply_addresses():
    payload = _greenhouse_payload(
        '<a href="mailto:apply@fictional.test">Apply to this role</a>'
        '<a href="mailto:careers@fictional.test">Apply another way</a>'
    )

    parsed = parse_greenhouse(payload, "Fictional Sciences")

    assert parsed[0].application_email is None


def test_greenhouse_accepts_repeated_identical_apply_addresses():
    payload = _greenhouse_payload(
        '<a href="mailto:apply@fictional.test">Apply to this role</a>'
        '<a href="mailto:apply@fictional.test">Apply again</a>'
    )

    parsed = parse_greenhouse(payload, "Fictional Sciences")

    assert parsed[0].application_email == "apply@fictional.test"


def test_greenhouse_ignores_plain_contact_addresses_without_mailto():
    payload = _greenhouse_payload("<p>Contact us: apply@fictional.test if you are interested.</p>")

    parsed = parse_greenhouse(payload, "Fictional Sciences")

    assert parsed[0].application_email is None


def test_lever_extracts_the_explicit_apply_mailto_anchor():
    payload = _lever_payload(
        '<p>Build fictional systems.</p><a href="mailto:apply@fictional.test">Apply to this role</a>'
    )

    parsed = parse_lever(payload, "Fictional Sciences")

    assert parsed[0].application_email == "apply@fictional.test"


def test_lever_ignores_plain_text_addresses_without_mailto():
    payload = _lever_payload("<p>Apply by writing to jobs@fictional-test.example.</p>")

    parsed = parse_lever(payload, "Fictional Sciences")

    assert parsed[0].application_email is None
