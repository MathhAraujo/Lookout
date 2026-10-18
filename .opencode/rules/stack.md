# Stack

- **Language**: Python 3.11+ (primary).
- **Domain**: AI agent for automatic job applications — likely involves
  scraping/browser automation, LLM integration and data persistence.

## Tooling

Defaults until the project defines otherwise:

- Tests: `pytest`
- Lint/format: `ruff check` / `ruff format`
- Virtual environment: `.venv` (must stay out of version control)

## Conventions

- Dependencies declared in `pyproject.toml` (preferred) or `requirements.txt`.
- Secrets and credentials only via environment variables / `.env` (never committed).
- Update this file as soon as real tooling choices are made (frameworks,
  package manager, task runner, CI).
