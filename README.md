# Lookout

An AI agent that automatically applies to job openings on your behalf.
Primarily written in Python.

> Status: Phase 1 MVP is implemented. See the [acceptance walkthrough](docs/runbooks/phase-1-acceptance.md)
> for verification results and credential-dependent integrations.

## Running (Phase 1 MVP)

Prerequisites: Docker with the Compose plugin. To start the local API, PostgreSQL,
and worker:

```bash
cp .env.example .env
mkdir -p data
cp -r templates/kb data/kb
```

Set `OPENROUTER_API_KEY` in `.env` before generating tailored resumes. Adzuna and
Gmail collection are optional and require their respective credentials.

```bash
docker compose up -d --build
curl http://localhost:8000/health
```

Collect synchronously or enqueue source jobs for the worker:

```bash
docker compose exec api python -m lookout.cli collect
docker compose exec api python -m lookout.cli collect --source remoteok
docker compose exec api python -m lookout.cli collect --source remoteok --enqueue
docker compose exec api python -m lookout.cli list-openings
docker compose exec api python -m lookout.cli tailor <OPENING_ID>
```

The API also supports `POST /collect` to enqueue all enabled sources or one
named source, `GET /openings` to list results, and
`POST /openings/{opening_id}/tailor` to enqueue resume generation.

## OpenCode setup

Agent configuration structure:

```
lookout/
├── opencode.jsonc          # Config: rules + Superpowers + MCPs (Context7, Playwright)
├── AGENTS.md               # General repository instructions
└── .opencode/
    ├── rules/              # Specific rules (.md files loaded automatically)
    │   ├── language.md     # Everything written in English
    │   ├── git-workflow.md # Conventional Commits + push at every major point
    │   ├── stack.md        # Stack and tooling (frozen per PRD)
    │   ├── privacy.md      # Personal data protection (data/ is gitignored)
    │   └── conventions.md  # Code conventions
    └── skills/             # Reusable skills (one folder per skill)
        └── skill-template/SKILL.md
```

- **Rules**: add any `.md` to `.opencode/rules/` — it takes effect on the next
  message exchange, no config changes needed.
- **Skills**: each skill is a folder with a `SKILL.md` (frontmatter with `name`
  and `description`). Docs: https://opencode.ai/v2/docs/skills
- **Superpowers** (plugin): registers methodology skills (brainstorming,
  writing-plans, TDD, systematic-debugging...). Requires restarting OpenCode
  after setup. Verify by asking: "Tell me about your superpowers".
- **Context7** (MCP): up-to-date library documentation. Works anonymously;
  for higher rate limits set the `CONTEXT7_API_KEY` env var and enable the
  commented header in `opencode.jsonc`. Verify with `opencode mcp list`.
- **Playwright** (MCP): browser automation for prototyping and testing
  job-board flows. First use may require `npx playwright install chromium`.
