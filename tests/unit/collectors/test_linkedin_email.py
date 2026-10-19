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
