# Phase 1 Acceptance Walkthrough

## Status

Partial acceptance. Steps 2–4 and 6 passed. Step 1 is blocked by local filesystem permissions and missing OpenRouter configuration in the running API container; Step 5 was not run. Optional Gmail step 7 was skipped because Gmail credentials are unavailable. Do not treat Phase 1 acceptance as complete until the remaining required step is verified.

No `.env` contents were displayed or recorded, and no personal knowledge-base data was read or recorded.

## Step 1: Prepare local data

- `.env` already existed, so it was preserved rather than overwritten.
- The running API container reported `OPENROUTER_API_KEY` absent. The `.env` value was not read.
- `data/kb` did not exist. Copying the fictional template failed because `data/` is owned by `root:root` with mode `755`, so the workspace user cannot write there. No ownership or permissions were changed.
- Result: blocked; configure the key and make the ignored local data directory writable before resuming.

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

Not run. The running API container did not have `OPENROUTER_API_KEY`, and the local KB template could not be copied into `data/kb`. No LLM request was made and no PDF was generated.

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
docker compose -f docker-compose.yml -f /tmp/opencode/lookout-compose-port-override.yml exec -T api pytest -v
docker compose -f docker-compose.yml -f /tmp/opencode/lookout-compose-port-override.yml exec -T api ruff check .
docker compose -f docker-compose.yml -f /tmp/opencode/lookout-compose-port-override.yml exec -T api ruff format --check apps tests
```

Observed: `60 passed, 2 warnings`; Ruff reported `All checks passed!`; formatter reported `68 files already formatted`. The warnings were dependency deprecations from WeasyPrint/harfbuzz and Starlette's TestClient integration.

Formatter verification is scoped to `apps` and `tests` per the repository workflow rule; generated Alembic files and documentation are excluded.

## Step 9: Commit and push

This partial report is being published as a documentation-only checkpoint. Task 16 remains open until the required real-LLM tailoring step is verified; final acceptance is still pending.
