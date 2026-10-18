# Privacy and Personal Data

This project processes sensitive personal data (resume, work history, courses,
languages, skills, job board credentials). Protect it accordingly.

## Rules

- The `data/` folder holds the local personal knowledge base (experience,
  courses, languages, skills, preferences). **Never commit its contents** —
  the folder is gitignored.
- Never commit real personal data: resumes, cover letters, profiles, real
  application answers, or screenshots containing personal information.
- Credentials for job boards and external services live only in `.env`
  (gitignored) or a secrets manager. Never hardcode credentials.
- Tests and fixtures must use **anonymized/fictional data** (fake names,
  fake companies, fake emails). Review fixtures before committing.
- Logs must not dump full personal payloads — redact sensitive fields.
- When sharing errors or screenshots (issues, chats, PRs), scrub personal
  data first.
