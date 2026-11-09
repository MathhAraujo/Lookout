# Lookout

An AI agent that automatically applies to job openings on your behalf.
Primarily written in Python.

> Status: Phase 1 MVP and the Phase 2 automation backend are implemented. See the
> [Phase 1](docs/runbooks/phase-1-acceptance.md) and
> [Phase 2](docs/runbooks/phase-2-acceptance.md) acceptance records for verification
> results and credential-dependent checks. The web frontend remains Phase 3.

## Running (Phase 1 MVP)

Prerequisites: Docker with the Compose plugin. To start the local API, PostgreSQL,
and worker:

```bash
cp .env.example .env
mkdir -p data
chmod 700 data
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

## LinkedIn alerts via Gmail (optional)

Place your Gmail desktop OAuth client file at `data/gmail_credentials.json`, then run:

```bash
docker compose exec api python -u -m lookout.cli gmail-auth
```

Open the printed authorization URL in your host browser. The callback uses
`http://localhost:8765/`, published only on loopback; set `GMAIL_AUTH_PORT` before
starting Compose if that port is occupied. The container does not need a browser.
OAuth requests Gmail read-only scope. The saved token file has owner-only access.

Label the relevant LinkedIn alert emails with `lookout/jobs`, enable
`linkedin_email` in `config/sources.yml`, and collect them. All pages of labeled
alerts are read, including older alerts after an outage; ingestion deduplicates
previously collected jobs. No LinkedIn scraping or submission is performed.

## Base resume and fixed personal header

The base resume is structured Markdown under `data/kb`, not a PDF sent to an LLM.
`identity.md` is the local-only header: name, email, phone, and address are inserted
by the renderer and remain identical across tailored versions. CPF is optional
and is never displayed in the resume. The model cannot read or edit the header.

Keep all personal/contact details in `identity.md`. Professional body files are
checked for accidental personal data before inference. The posting is redacted
separately. Never put credentials or additional personal details in body files.

The model selects and orders approved experience/project IDs, numbered highlights,
and skills. It cannot author new resume text. The application resolves those
selections against the base resume, rejecting unknown IDs, invented skills,
out-of-range highlights, and extra fields. Summary, education, and languages
remain permanent sections. This prioritizes factual correctness over free-form
rewriting in Phase 1.

Set `language: en` or `language: pt-br` in the frontmatter of the root `summary.md`.
For the other posting language, maintain an approved body under
`data/kb/translations/<language>/` with the same body-file structure and its own
`summary.md` language marker. The root header is shared by both languages.
The starter template includes English and Brazilian Portuguese examples; replace
all fictional content in both versions with your approved facts. Missing
translations fail before inference rather than generating a mixed-language PDF.

Only the final PDF receives the local header. Failed generation preserves any
previous PDF and never publishes a partially written file.

## Phase 2 local services and credentials

The default `docker-compose.yml` starts only PostgreSQL, API, and worker.
Optional Phase 2 services are defined in `docker-compose.phase2.yml`.
Before starting the full stack, set unique local values for `MINIO_ACCESS_KEY`
and `MINIO_SECRET_KEY` in `.env`. Generate the Infisical server keys locally and
copy the output into the same ignored file; do not commit or paste these values
into source files:

```bash
python -c "import secrets; print('MINIO_ACCESS_KEY=' + secrets.token_hex(16)); print('MINIO_SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('INFISICAL_ENCRYPTION_KEY=' + secrets.token_hex(16)); print('INFISICAL_AUTH_SECRET=' + secrets.token_urlsafe(32))"
```

Start the optional stack after configuring its secrets:

```bash
docker compose -f docker-compose.yml -f docker-compose.phase2.yml up -d --build
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
`/application`; configure `SMTP_HOST`, `SMTP_PORT` (STARTTLS, usually 587), and `SMTP_FROM` in `.env`.
Set `SMTP_USERNAME` when the authentication user differs from the sender address.
TLS and authentication must succeed before any application email is sent.
Never put SMTP or job-board passwords in `.env.example`, logs, or application
records.

Initialize Greenhouse and Lever browser profiles manually from the repository
root on a host with the Python package, Playwright Chromium, a desktop display,
and an interactive terminal:

```bash
python -m lookout.cli browser-auth greenhouse
python -m lookout.cli browser-auth lever
```

Profiles stay under the ignored `data/browser-profiles/` directory. Complete
Google SSO or password login by hand; CAPTCHA and 2FA are never automated.
The default containers have no desktop display; run browser authentication on
the host, or supply your own display configuration for interactive containers.
Dry-run remains enabled by default. Real submission requires both
`DRY_RUN=false` and `AUTO_SUBMIT_ENABLED=true`.

## Phase 2 workflow operations

Prepare your local matching preferences and approved screening answers before
enabling automatic matching. The template values are fictional:

```bash
cp -n templates/match-profile.yml data/match-profile.yml
cp -n templates/facts.yml data/facts.yml
```

Set both `OPENROUTER_TAILORING_MODEL` and `OPENROUTER_SCORING_MODEL` in `.env`.
They may use the same selected model, including a free model that passes the
structured-output checks. No fallback to another paid model is selected by the
application.

The Phase 2 Compose overlay enables `WORKFLOW_ENABLED=true`. Without the overlay,
the setting defaults to `false`, preserving standalone Phase 1 operation.
Explicit `match` commands can also enqueue matching while automatic matching is
disabled. Collection inserts and their matching jobs commit together; repeated
collection and backfill do not create duplicate decisions.

```bash
docker compose exec api python -m lookout.cli match --backfill
docker compose exec api python -m lookout.cli list-applications --lane review
docker compose exec api python -m lookout.cli approve <APPLICATION_ID>
docker compose exec api python -m lookout.cli decline <APPLICATION_ID>
docker compose exec api python -m lookout.cli check-connectors
```

New openings pass through deterministic filtering and scoring. Rejected openings
receive no PDF. Review and manual-assist items receive a PDF in MinIO; only
auto-apply items and approved reviews proceed to form inspection and screening.
Identity fields are resolved locally, and unknown required questions block
submission. Answer text stays in MinIO, with only answer metadata in PostgreSQL.
Reviews expire after seven days; the worker checks expiry hourly and connector
health daily.

The API exposes:

- `GET /applications?lane=review&status=awaiting_review&limit=100&offset=0`
- `GET /applications/{id}` with the opening's company, title, and source URL
- `POST /applications/{id}/approve` and `POST /applications/{id}/decline`
- `GET /applications/{id}/artifacts` for metadata and artifact IDs
- `GET /artifacts/{artifact_id}` for an integrity-checked PDF or JSON download
- `GET /connectors/health` for persisted connector health

A submission is recorded as `submitting` before external I/O. An interrupted or
ambiguous submission goes to manual-assist and is never automatically replayed.
Missing secrets, unavailable sessions, and unsupported required form controls
also produce a manual-assist reason. Retrying a final record upload does not
repeat a completed submission. Changes to submission flags do not replay items
already completed in dry-run.

## Development verification

The full suite also covers the optional Phase 2 browser adapters. Include browser
binaries in the API image when running that suite; the default MVP images omit
them to keep startup smaller:

```bash
docker compose build --build-arg INSTALL_BROWSERS=true api
docker compose up -d --no-build
docker compose exec api pytest -q
docker compose exec api ruff check .
docker compose exec api ruff format --check apps tests
```

For an isolated smoke environment with fictional KB files, no host data mounts,
and a random loopback API port:

```bash
docker compose --env-file .env.example -p lookout-phase1-acceptance \
  -f docker-compose.yml -f docker/acceptance/phase1.override.yml up -d --build
```

The acceptance override creates a separate PostgreSQL volume and uses only the
committed fictional template. It does not load `.env` credentials or `data/`.
See the runbook for the exact scope of the latest verification.

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
