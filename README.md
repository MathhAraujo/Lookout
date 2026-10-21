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

## Phase 2 local services and credentials

Before starting the full stack, set unique local values for `MINIO_ACCESS_KEY`
and `MINIO_SECRET_KEY` in `.env`. Generate the Infisical server keys locally and
copy the output into the same ignored file; do not commit or paste these values
into source files:

```bash
python -c "import secrets; print('MINIO_ACCESS_KEY=' + secrets.token_hex(16)); print('MINIO_SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('INFISICAL_ENCRYPTION_KEY=' + secrets.token_hex(16)); print('INFISICAL_AUTH_SECRET=' + secrets.token_urlsafe(32))"
```

The Infisical web interface is available at `http://localhost:8081`; the API
binds to loopback at `http://localhost:8000`. Redis is an internal dependency
for Infisical only and is not used for the Lookout job queue. MinIO is built
locally from a pinned official source release, and neither its S3 endpoint nor
its console is published on the host.

The PostgreSQL initialization script creates the separate `infisical` database
for fresh volumes. For an existing Phase 1 volume, first check whether the
database already exists:

```bash
docker compose exec postgres psql -U lookout -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'infisical'"
```

Only if that command returns no row, create it once without changing the
existing Lookout database:

```bash
docker compose exec postgres createdb -U lookout infisical
```

On first launch, create a local Infisical project and `dev` environment, then
create a Universal Auth machine identity with read-only access to the
`/application` secret path. Keep `INFISICAL_URL` set to the internal Compose
address `http://infisical:8080`. Put the identity's client ID, client secret,
project ID, and environment in `.env`. Store `SMTP_PASSWORD` only in Infisical at
`/application`; configure `SMTP_HOST`, `SMTP_PORT`, and `SMTP_FROM` in `.env`.
Never put SMTP or job-board passwords in `.env.example`, logs, or application
records.

After the Phase 2 CLI command is available, initialize Greenhouse and Lever
browser profiles manually:

```bash
docker compose exec api python -m lookout.cli browser-auth greenhouse
docker compose exec api python -m lookout.cli browser-auth lever
```

Profiles stay under the ignored `data/browser-profiles/` directory. Complete
Google SSO or password login by hand; CAPTCHA and 2FA are never automated.
Dry-run remains enabled by default. Real submission requires both
`DRY_RUN=false` and `AUTO_SUBMIT_ENABLED=true`.

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
