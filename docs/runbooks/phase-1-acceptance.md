# Phase 1 Acceptance Walkthrough

## Status

Acceptance passed for the required walkthrough. Steps 1–6 and 8 passed; optional Gmail step 7 was skipped because Gmail credentials are unavailable. The first LLM response failed schema validation; after the prompt fix, a retry produced a PDF that was reviewed. No model-generated code was executed.

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

The first request with `minimax/minimax-m3.1-flash:free` returned JSON without required `language` and `experiences` fields; Pydantic rejected it and no PDF was written. The prompt was updated to specify the exact `TailoredResume` JSON shape. After the user authorized retries, the second request produced `data/artifacts/2af51bdc-4151-4c23-a6cc-78ffd1fae50a.pdf`.

PDF review: one page with 1,214 characters of selectable text; English headings and KB-supported skills were present. The content was checked against the fictional KB; no unsupported facts were found. The PDF was generated locally by the application, not by executing model-generated code.

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

Observed: `62 passed, 2 warnings`; Ruff reported `All checks passed!`; formatter reported `69 files already formatted`; both API and worker images built successfully. The warnings were dependency deprecations from WeasyPrint/harfbuzz and Starlette's TestClient integration.

Formatter verification is scoped to `apps` and `tests` per the repository workflow rule; generated Alembic files and documentation are excluded.

## Step 9: Commit and push

The acceptance results are recorded here and in `docs/PLAN-PHASE-1.md`; this checkpoint is committed and pushed to the project branch.
