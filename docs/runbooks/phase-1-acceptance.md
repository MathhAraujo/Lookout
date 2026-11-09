# Phase 1 Acceptance Walkthrough

## Live selection-contract acceptance — 2026-11-09

The previously pending live OpenRouter check passed with the configured free
model using fictional facts. The approved-selection pipeline generated one-page
EN and PT-BR PDFs with selectable text and the fixed local header. Structured
scoring also returned a valid response. See the Phase 2 acceptance record for
the model, observed PDF measurements, and complete verification scope.

The November 5 section below remains the historical record of that execution;
its live-model pending status was resolved by this later check. Gmail, Adzuna,
and authorized live ATS forms remain credential/configuration-dependent.

## Re-acceptance — 2026-11-05

Implementation and local regression gates passed. Live OpenRouter acceptance for
the new selection contract remains pending: no API key was configured during
this run. The fictional EN/PT-BR PDFs below used HTTP-stubbed inference, not a
real model response. Gmail/Adzuna and curated ATS live checks remain dependent
on user credentials/configuration. The historical walkthrough follows this
section and is not evidence of a real-model call with the new contract.

### Scope and privacy boundary

- `identity.md` is local-only. The LLM receives professional `ResumeContent` and
  the redacted posting, never the header.
- Strict fact selection replaces model-authored resume text. IDs, highlight
  indices, and skills are checked before local rendering. Permanent sections
  and header values come from approved local files.
- Approved `translations/pt-br/` content is included in the fictional template;
  missing translations stop generation before inference.
- Regressions cover formatted identity variants, header edits, invented facts,
  posting-language mismatch, atomic PDF failure/permissions, concurrent ingestion,
  source transaction rollback, changed external IDs, technology distinctions,
  bounded stale retries, heartbeats, stale-attempt fencing, and Gmail pagination.
- The two previously identified Phase 2 defects were also corrected: SMTP now
  requires TLS/authentication, and expired reviews cannot be approved before
  scheduled cleanup.

### Full regression gates

A temporary Python 3.13 environment installed the project with `.[dev]`. Tests
used an isolated PostgreSQL 16 database whose name ends in `_test`.

```bash
pytest -q
ruff check .
ruff format --check apps tests
```

Results: **293 passed**, one Starlette/TestClient dependency deprecation warning;
Ruff passed; **111 files already formatted**. Both Python 3.12 API and worker
images built successfully. The host suite includes local Chromium-backed
Greenhouse/Lever fixture tests; no real application was submitted.

The API-to-worker acceptance test exercises collection twice, exact persisted
job completion, HTTP JSON inference, and a real text PDF with a fixed header:
`tests/integration/test_phase1_acceptance.py`.

### Isolated Docker startup and migrations

```bash
docker compose --env-file .env.example -p lookout-phase1-acceptance \
  -f docker-compose.yml -f docker/acceptance/phase1.override.yml up -d --build
docker compose --env-file .env.example -p lookout-phase1-acceptance \
  -f docker-compose.yml -f docker/acceptance/phase1.override.yml ps
docker compose --env-file .env.example -p lookout-phase1-acceptance \
  -f docker-compose.yml -f docker/acceptance/phase1.override.yml exec -T api alembic check
```

Observed: only PostgreSQL, API, and worker started. PostgreSQL and API became
healthy; worker ran. Startup applied migrations through `0003`; `alembic check`
reported `No new upgrade operations detected.` HTTP health returned
`200 {"status": "ok"}`. The random host API port was 32770, then 32771 after the final image
recreation; health returned HTTP 200 again.

The override uses committed fictional templates, an independent PostgreSQL
volume, no host data mounts, and `.env.example`. Personal KB files and real
credentials were not loaded by the acceptance stack.

### Live collection and API-to-worker path

The isolated API container ran `python -m lookout.cli collect --source remoteok`.
Observed: `fetched=99`, `inserted=99`, `duplicates=0`, `skipped=0`, `errors=[]`.

A subsequent `POST /collect` with `{"source":"remoteok"}` returned
`202 {"enqueued":1}`. The live worker completed the job with `attempts=1` and
no `last_error`. The RemoteOK row count remained 99, confirming deduplication on
the repeated collection. Separate fictional openings were used only for PDF
smoke checks.

### Container PDF smoke checks

Using `templates/kb`, `OpenRouterClient` with an `httpx.MockTransport`, and the
real pipeline/WeasyPrint/PDF reader inside the API container:

| Language | Pages | Selectable text characters | Header present locally | Header in inference |
| --- | --- | --- | --- | --- |
| EN | 1 | 684 | Yes | No |
| PT-BR | 1 | 687 | Yes | No |

The final images reproduced the same results after the PDF permission fix. New
PDFs were readable with mode `0644` inside the isolated container; the normal
quickstart makes the host data directory owner-only (`0700`), and replacements
preserve an existing PDF's explicit permissions.

These checks validate rendering and the application-side inference contract;
they do not validate a live OpenRouter model's ability to follow that contract.
The local-header/approved-content decision and its deliberate free-form
rewriting limitation are recorded in ADR-0001.

### Cleanup

Only acceptance-created containers and volumes are removed with the matching
isolated project name. Production/default project data is untouched:

```bash
docker compose --env-file .env.example -p lookout-phase1-acceptance \
  -f docker-compose.yml -f docker/acceptance/phase1.override.yml down -v
```

## Historical acceptance baseline

Acceptance passed for the required walkthrough. Steps 1–6 and 8 passed; optional Gmail step 7 was skipped because Gmail credentials are unavailable. After the whole-branch review, the privacy, factual-validation, deduplication, and source-schema safeguards were strengthened and verified. No model-generated code was executed.

The API key value was only checked for presence; it was never displayed or recorded. No personal knowledge-base data was read or recorded.

## Step 1: Prepare local data

- `.env` was created from `.env.example`; `OPENROUTER_API_KEY` was set and `OPENROUTER_TAILORING_MODEL` was `minimax/minimax-m3.1-flash:free`.
- `data/` remains owned by `root:root` with mode `755`. The fictional template was copied to `data/kb` from a one-off Compose container running as root; host ownership and permissions were not changed.
- Result: prepared with the fictional KB. The host workspace user still cannot edit files under `data/` directly.

## Step 2: Boot the stack

Command (using the existing temporary Compose override because host port 8000 was occupied):

```bash
docker compose -f docker-compose.yml -f /tmp/opencode/lookout-compose-port-override.yml up -d --build
docker compose -f docker-compose.yml -f /tmp/opencode/lookout-compose-port-override.yml ps
docker compose -f docker-compose.yml -f /tmp/opencode/lookout-compose-port-override.yml exec -T api alembic current
```

Observed: Postgres healthy, API healthy on `8001 -> 8000`, worker running; Alembic reported `0002 (head)`.

## Step 3: Collect RemoteOK openings

Command:

```bash
docker compose -f docker-compose.yml -f /tmp/opencode/lookout-compose-port-override.yml exec -T api python -m lookout.cli collect --source remoteok
```

First run: `fetched=99`, `inserted=99`, `duplicates=0`, `skipped=0`, `errors=[]`.

Repeated the same command: `fetched=99`, `inserted=0`, `duplicates=99`, `skipped=0`, `errors=[]`.

Result: passed; repeated listings were deduplicated.

## Step 4: Collect all enabled sources

Command:

```bash
docker compose -f docker-compose.yml -f /tmp/opencode/lookout-compose-port-override.yml exec -T api python -m lookout.cli collect
```

Observed per-source stats (`fetched / inserted / duplicates / errors`):

| Source | Stats |
| --- | --- |
| RemoteOK | 99 / 0 / 99 / none |
| Remotive | 12 / 10 / 2 / none |
| Arbeitnow | 300 / 291 / 9 / none |
| Jobicy | 200 / 198 / 2 / none |
| We Work Remotely | 91 / 88 / 3 / none |
| Working Nomads | 41 / 25 / 16 / none |
| Himalayas | 20 / 20 / 0 / none |
| HN Who Is Hiring | 580 / 579 / 1 / none |
| Greenhouse | 0 / 0 / 0 / none |
| Lever | 0 / 0 / 0 / none |

Result: passed; all configured collectors returned stats without aborting the run. Disabled or unconfigured sources were not called.

## Step 5: Tailor a resume with a real LLM call

The CLI initially printed empty objects from `list-openings`. Root cause: ORM models were serialized after the session closed and expired their fields. Serialization now occurs inside the session, covered by `test_list_openings_prints_fields_after_session_closes`.

The first request with `minimax/minimax-m3.1-flash:free` returned JSON without required `language` and `experiences` fields; Pydantic rejected it and no PDF was written. After the prompt was updated with the exact `TailoredResume` JSON shape, a second request produced a PDF. Whole-branch review then led to stricter validation requiring summaries to match one KB fact verbatim and highlights to match the referenced KB entry. A third request with those constraints produced the final `data/artifacts/2af51bdc-4151-4c23-a6cc-78ffd1fae50a.pdf`.

PDF review: one page with 754 characters of selectable text; English headings and KB-supported skills were present. Validation enforced exact KB source facts before rendering. The PDF was generated locally by the application, not by executing model-generated code.

## Step 6: Verify the API-to-worker queue

The repository maps the API to host port 8001 in this environment because port 8000 is occupied.

```bash
curl -sS -X POST http://localhost:8001/collect \
  -H 'Content-Type: application/json' \
  -d '{"source":"remoteok"}'
```

Observed: HTTP 202 with `{"enqueued":1}`. The corresponding Postgres job reached `status=done` with `attempts=1`.

Result: passed.

## Step 7: Gmail OAuth and LinkedIn alerts (optional)

Skipped. `data/gmail_credentials.json` was not present, so OAuth was not started and LinkedIn email collection was not enabled.

## Step 8: Full verification

Commands:

```bash
docker compose run --rm --no-deps api pytest -q
docker compose run --rm --no-deps api ruff check .
docker compose run --rm --no-deps api ruff format --check apps tests
docker compose build api worker
```

Observed: `80 passed, 2 warnings`; Ruff reported `All checks passed!`; formatter reported `70 files already formatted`; both API and worker images built successfully. The warnings were dependency deprecations from WeasyPrint/harfbuzz and Starlette's TestClient integration.

Review hardening: international `+`-prefixed phone numbers are redacted and detected; unsupported summaries/highlights are rejected before PDF rendering; seniority/grade markers prevent distinct roles from deduplicating; unexpected top-level collector payload shapes are surfaced as source errors.

Formatter verification is scoped to `apps` and `tests` per the repository workflow rule; generated Alembic files and documentation are excluded.

## Step 9: Commit and push

The acceptance results are recorded here and in `docs/PLAN-PHASE-1.md`; this checkpoint is committed and pushed to the project branch.
