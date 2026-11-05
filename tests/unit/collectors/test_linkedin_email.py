from pathlib import Path

from lookout.collectors.linkedin_email import parse_linkedin_alert


def test_parse_linkedin_alert_extracts_canonical_jobs():
    html = Path("tests/fixtures/sources/linkedin_alert.html").read_text()
    jobs = parse_linkedin_alert('2 new jobs for "python remote"', html)

    assert [(job.company, job.title) for job in jobs] == [
        ("Globex", "Senior Python Engineer"),
        ("Initech", "Backend Developer"),
    ]
    assert jobs[0].external_id == "4311001"
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/4311001"
    assert jobs[0].source == "linkedin_email" and jobs[0].posted_at is None
    assert jobs[0].raw == {"subject": '2 new jobs for "python remote"'}


def test_parse_linkedin_alert_ignores_non_job_emails():
    assert parse_linkedin_alert("Your weekly summary", "<html><body>No jobs</body></html>") == []


def test_gmail_fetch_reads_all_pages_without_a_seven_day_cutoff(monkeypatch):
    import base64
    from unittest.mock import MagicMock

    from lookout.collectors.linkedin_email import LinkedInEmailCollector
    from lookout.config import Settings

    service = MagicMock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.side_effect = [
        {"messages": [{"id": "older-alert"}], "nextPageToken": "page-two"},
        {"messages": [{"id": "newer-alert"}]},
    ]
    html = Path("tests/fixtures/sources/linkedin_alert.html").read_bytes()
    messages.get.return_value.execute.return_value = {
        "payload": {
            "mimeType": "text/html",
            "headers": [],
            "body": {"data": base64.urlsafe_b64encode(html).decode()},
        }
    }
    monkeypatch.setattr("lookout.collectors.linkedin_email.load_gmail_credentials", lambda _: None)
    monkeypatch.setattr("lookout.collectors.linkedin_email.build", lambda *args, **kwargs: service)
    jobs = LinkedInEmailCollector(Settings()).fetch()
    assert len(jobs) == 4
    calls = messages.list.call_args_list
    assert len(calls) == 2 and calls[1].kwargs["pageToken"] == "page-two"
    assert "newer_than" not in calls[0].kwargs["q"]
    assert messages.get.call_count == 2
