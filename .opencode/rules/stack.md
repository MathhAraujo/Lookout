# Stack

> Provisional — decisions are finalized in the PRD (`docs/`). Update this file
> as choices land.

## Backend / agent

- **Python 3.11+**
- **BentoML** (or FastAPI if needed) for the agent and backend structure
- Storage: **SQLite** if a classic SQL database is needed; open to alternatives
  (e.g. a Markdown/Obsidian-style knowledge base) — pending the PRD
- The personal knowledge base lives in `data/` (local only, gitignored —
  see the privacy rule)

## Frontend

- **React + Vite + TanStack (Query/Router) + TypeScript**
- **Bun** as package manager/runtime
- Scope for now: basic UI to configure job extraction parameters

## Infrastructure

- Runs locally or on a self-hosted homelab (24 GB RAM, i3-1215u) —
  keep resource usage modest; prefer lightweight models/services

## Tooling

- Python tests: `pytest` · lint/format: `ruff check` / `ruff format`
- Frontend: `bun` scripts (dev/build/test) — update once scaffolded
- Virtual environment: `.venv` (never committed)
