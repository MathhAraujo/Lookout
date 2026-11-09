# Stack

## Backend / agent

- **Python 3.11+** (containers use Python 3.12) and **FastAPI**.
- **PostgreSQL** with SQLModel and Alembic migrations; no SQLite in app code.
- A PostgreSQL-backed `jobs` table and dedicated worker process, scheduled with
  APScheduler. Redis is not used.
- **Playwright** browser automation is implemented in the optional Phase 2 stack.
- **WeasyPrint** renders Jinja2 HTML/CSS resumes to PDF.
- **OpenRouter** is the external LLM gateway; only inference leaves the machine.
- **Gmail API** reads LinkedIn job-alert email using read-only OAuth scope.
- **rapidfuzz** performs normalized company/title deduplication.
- **Infisical** stores application credentials in Phase 2. Bootstrap settings and
  inference keys come from `.env`; SMTP passwords are read from the vault.
- The personal knowledge base lives in `data/` (local only, gitignored — see
  the privacy rule).

## Frontend

- React + Vite + TanStack (Query/Router) + TypeScript, managed with **Bun**.
- Frontend implementation is deferred to Phase 3.

## Infrastructure

- **Docker Compose** runs PostgreSQL, API, and worker in Phase 1. The optional
  Phase 2 overlay adds MinIO and Infisical, plus Infisical's internal Redis.
- Keep resource usage modest for local and self-hosted deployments.

## Tooling

- Python tests: `pytest` · lint/format: `ruff check` / `ruff format`.
- Virtual environment: `.venv` (never committed).
