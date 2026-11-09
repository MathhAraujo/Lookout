# Phase 2 Acceptance Walkthrough

Status: isolated Phase 2 dry-run acceptance passed on 2026-11-09. Credential-dependent
external checks are listed separately below; no real application was submitted.

## Verification already completed — 2026-11-09

- Full suite inside the Python 3.12 API image with real PostgreSQL/MinIO:
  **349 passed** in 59.56 seconds, two dependency deprecation warnings.
- Ruff lint passed; formatter check passed for **118 files**.
- Python wheel build passed.
- The workflow/operational tests passed against real PostgreSQL 16 and MinIO.
- A binary object survived a MinIO container restart byte for byte.
- HTTP-stubbed inference plus real Chromium exercised API collection, deduplication,
  scoring, local identity resolution, form screening/filling, zero final POSTs,
  stored PDFs/answers/records, and integrity-checked artifact downloads.
- Recovery regressions cover a crash after submission, an obsolete worker lease,
  concurrent application processing, and final-record upload retries without
  repeating a completed submission.

## Final review and answer-scope safeguards

The independent whole-branch review identified three important findings; all
were addressed in one regression-backed fix pass:

- Qualified or inverted factual questions now require an explicit
  `question:<wording>` approval. Only an enumerated set of unqualified questions
  may use a generic class fact. The context normalizer preserves C/C++/C# and
  currency symbols. Identity fields also require a matching identity label.
- Reopened forms are checked against their inspected question/control signatures
  and effective destination before filling and again before a final click.
  Changed labels, required flags, input types, option values, and destinations
  downgrade to manual-assist.
- Unexpected browser inspection failures retain the prepared PDF, store a
  sanitized error, and downgrade to manual-assist instead of exhausting retries
  while appearing ready.

The new regressions were observed failing before the fixes. No minor findings
were deferred. Existing Tasks 1–7 were reused and regression-tested, rather than
rebuilt. Automatic matching remains opt-in outside the Phase 2 Compose overlay;
more specific questions intentionally require local user approval.

## Live fictional OpenRouter check

The configured free model, `nvidia/nemotron-3.5-super-vl:free`, passed the new
approved-fact selection contract. Only fictional professional facts and redacted
postings were sent. Identity headers were rendered locally.

| Check | Observed result |
| --- | --- |
| English resume | 1 page, 511 selectable text characters, fixed header present |
| Brazilian Portuguese resume | 1 page, 619 selectable text characters, fixed header present |
| Structured scoring | Valid score 80 and review lane for the fictional opening |

These results validate the response contract; a single score is not a match-quality
benchmark. No actual job application or recruiter message was sent.

## Observed complete-stack checks

- PostgreSQL, MinIO, Infisical Redis, Infisical, and API became healthy; the regular
  worker started. MinIO bucket initialization exited successfully.
- Infisical `/api/status` and API `/health` returned HTTP 200.
- Startup applied Alembic through `0003`; `alembic check` reported no new upgrade
  operations. The API and worker Docker images built successfully. Both images
  matched the verified working tree for all 57 packaged Python/config/template files.
- The separate fixture worker drove all four lanes through the live API/database.
  Approving a prepared review moved it to dry-run; repeating approval returned 409.
  Three resume PDFs were downloaded through the API. Final form POST count: **0**.
- Persisted fictional events contained no direct identity, credentials, or answer
  payloads; PostgreSQL answer rows have no answer-text column.
- Seven-day expiry, decline, missing facts/secrets, expired browser sessions,
  unsupported required controls, and idempotency were exercised by regression tests.

## Reproduce the isolated stack

Run from the repository root. Generate a temporary acceptance environment with
unique service keys; this does not load the personal `.env` or `data/` directory:

```bash
LOOKOUT_ACCEPTANCE_ENV=$(mktemp /tmp/lookout-phase2-acceptance.XXXXXX)
python3 - "$LOOKOUT_ACCEPTANCE_ENV" <<'PYTHON'
import secrets
import sys
from pathlib import Path

values = Path(".env.example").read_text()
values += "\nMINIO_ACCESS_KEY=" + secrets.token_hex(16)
values += "\nMINIO_SECRET_KEY=" + secrets.token_urlsafe(32)
values += "\nINFISICAL_ENCRYPTION_KEY=" + secrets.token_hex(16)
values += "\nINFISICAL_AUTH_SECRET=" + secrets.token_urlsafe(32) + "\n"
Path(sys.argv[1]).write_text(values)
PYTHON

lookout_acceptance() {
  docker compose --env-file "$LOOKOUT_ACCEPTANCE_ENV" -p lookout-phase2-acceptance \
    -f docker-compose.yml -f docker-compose.phase2.yml \
    -f docker/acceptance/phase2.override.yml "$@"
}
lookout_acceptance up -d --build
lookout_acceptance ps
lookout_acceptance exec -T api alembic check
```

The override uses fictional templates, separate service volumes, a random loopback
API port, and test-only mounts. It exposes no MinIO or Infisical host port. The
acceptance worker has no real API key, and both submission flags are forced safe.

Run the complete regression suite inside the API image, using real MinIO for the
workflow tests. Environment values are expanded only inside the container:

```bash
lookout_acceptance exec -T api sh -c 'TEST_MINIO_ENDPOINT_URL="$MINIO_ENDPOINT_URL" TEST_MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" TEST_MINIO_SECRET_KEY="$MINIO_SECRET_KEY" pytest -q'
lookout_acceptance exec -T api ruff check .
lookout_acceptance exec -T api ruff format --check apps tests
```

The test image includes installed application code and Chromium; the acceptance
override mounts the tests. Phase 1 acceptance explicitly disables the workflow so
it remains valid even when the containing stack enables Phase 2.

For the live API/dedicated-worker smoke, stop only this isolated project's regular
worker. The smoke starts its own worker process with a local HTTP inference
fixture and fictional forms, then shuts that process down:

```bash
lookout_acceptance stop worker
lookout_acceptance exec -T api python -m tests.support.phase2_smoke
lookout_acceptance start worker
```

## Credential-dependent scope

- The live OpenRouter check used the user's configured model/key only for
  inference with fictional approved professional content. No key was recorded.
- Gmail/Adzuna and authorized live ATS forms were not exercised during this
  acceptance. Their credentials/company configuration remain local setup steps.
- Infisical service health is checked against the real local service; successful
  retrieval through a user-provisioned machine identity and real SMTP delivery
  require local vault/mail-account setup. SDK/error behavior and required SMTP
  TLS/authentication are covered by fictional unit tests.
- No real job application, email application, recruiter message, CAPTCHA bypass,
  or automated login was performed.

## Cleanup

Remove only the named acceptance project and its fixture volumes, then remove the
same temporary environment file created above:

```bash
lookout_acceptance down -v
rm "$LOOKOUT_ACCEPTANCE_ENV"
```

Personal `.env`, knowledge-base files, browser profiles, and default project data
are outside this acceptance stack.
