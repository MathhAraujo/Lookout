# Phase 2 — Automation Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Phase 1 collector and resume-tailoring MVP into the PRD's automation loop: score openings, route them into lanes, prepare and screen applications, and submit only through supported Greenhouse, Lever, or explicit email-application paths.

**Architecture:** Keep the existing Python package, PostgreSQL-backed queue, and dedicated worker. Add persistent application decisions and audit history, MinIO-backed artifacts, an OpenRouter scoring path, a facts-gated screener, and Playwright/email appliers. Expose review and operational controls through the existing API and CLI; do not add the Phase 3 web frontend.

**Tech Stack:** Python 3.11+ (containers use 3.12), FastAPI, SQLModel, PostgreSQL 16, Alembic, APScheduler, OpenRouter, Playwright Python, Infisical Python SDK, MinIO through the S3-compatible Boto3 client, WeasyPrint, pytest, and Ruff.

**Spec:** `docs/PRD.md` §§4–7 and §11; build on the Phase 1 baseline in `docs/PLAN-PHASE-1.md` and its accepted behavior in `docs/runbooks/phase-1-acceptance.md`.

## Global Constraints

- Python ≥ 3.11; containers use Python 3.12.
- PostgreSQL with SQLModel and Alembic; no SQLite in application code.
- Keep the Lookout queue in PostgreSQL's `jobs` table with APScheduler; Redis is not a Lookout queue. If the selected self-hosted Infisical release requires Redis, use it only as Infisical's internal dependency.
- Use Playwright with `launch_persistent_context` for browser sessions. Never launch concurrent browser processes against the same user-data directory.
- Prefer Google SSO for platform login wherever it is offered; otherwise keep credentials in the local Infisical vault and never automate CAPTCHA/2FA.
- Use Jinja2 HTML/CSS → WeasyPrint for tailored resumes and OpenRouter for external LLM inference.
- Direct PII (name, CPF, phone, address) must never be sent to an external LLM; retain the existing redaction-and-post-redaction assertion on every LLM call.
- The knowledge base remains the source of resume facts. The screener may infer only the enumerated subjective answer classes below; it must not invent factual answers.
- Supported automatic application targets are Greenhouse, Lever, and an explicit application email. LinkedIn remains email-alert ingestion only; Gupy and reapplication to a previously applied opening remain out of scope.
- Dry-run is enabled by default. A final submit requires both `DRY_RUN=false` and `AUTO_SUBMIT_ENABLED=true`, plus an eligible `auto_apply` decision or explicit review approval.
- MinIO, Infisical, PostgreSQL, API, and worker run locally through Docker Compose. Application submission is the only planned non-LLM data egress, and only to the opening's explicit application destination.
- Credentials and persistent browser profiles are local-only; never commit `.env`, `data/`, browser profiles, real resumes, application answers, or personal screenshots. Tests and fixtures use fictional/anonymized data only.
- Do not implement the React frontend, credential-management UI, recruiter messaging, interview tracking, or post-application follow-up in Phase 2. The UI remains Phase 3.
- All repository artifacts, code, comments, and commit messages are in English. Use Conventional Commits.
- Before each milestone commit, run the full test suite, `ruff check .`, and `ruff format --check apps tests`; do not format generated Alembic files or documentation.

## Review Focus

1. **Incomplete or conflicting profile data** (empty include list, unknown work mode, missing salary, currency mismatch) must not reject an otherwise eligible opening silently. Pin defaults and explainable outcomes in Task 3 tests.
2. **Malformed or unsafe scoring output** (out-of-range score, invalid JSON, PII in profile/posting) must fail closed without leaking PII or routing to auto-apply. Pin in Task 3 tests.
3. **Unknown or disqualifying application questions** must block submission when no exact approved fact exists; optional unknown questions may be left blank. Pin in Task 5 tests.
4. **Expired sessions, CAPTCHA/2FA, changed forms, or connector outages** must downgrade to manual-assist and surface a health/error state without dumping personal payloads. Pin in Tasks 6–7 tests.
5. **Retries, ambiguous submit results, and dry-run** must never cause a duplicate or unintended submission. Persist the pre-submit state before network submission and pin this in Tasks 7–8 tests.

## File Structure

- `apps/api/lookout/models.py`, `applications.py`, and `alembic/versions/0003_phase_2_workflow.py` own the durable workflow state, transitions, and audit history.
- `apps/api/lookout/artifacts.py` owns the S3-compatible storage interface; `docker-compose.yml` adds MinIO and its bucket initialization.
- `apps/api/lookout/matching.py`, `match_profile.py`, `config/matching.yml`, and `templates/match-profile.yml` own deterministic filtering, scoring, and profile/policy loading.
- `apps/api/lookout/facts.py` and `screener.py`, plus `templates/facts.yml`, own approved facts and answer-resolution policy.
- `apps/api/lookout/secrets.py`, `browser_sessions.py`, and `connector_health.py` own Infisical access, persistent browser profiles, and connector health.
- `apps/api/lookout/appliers/` owns the common application contract and Greenhouse, Lever, and email connectors.
- Existing `worker.py`, `api.py`, `cli.py`, `ingest.py`, and `config.py` connect the modules to the queue, review operations, and settings; Phase 1 CLI/API behavior remains compatible.
- `tests/unit/` and `tests/integration/` cover the new interfaces with fake LLMs, mocked S3/SMTP, fictional records, and local HTML forms. `docs/runbooks/phase-2-acceptance.md` records acceptance commands/results without personal data.

---

### Task 1: Workflow persistence and transition repository

**Files:**
- Modify: `apps/api/lookout/models.py`
- Modify: `apps/api/lookout/openings.py`
- Modify: `apps/api/lookout/collectors/base.py`
- Create: `apps/api/lookout/applications.py`, `alembic/versions/0003_phase_2_workflow.py`, `tests/integration/test_applications.py`
- Test: `tests/integration/test_applications.py`

**Interfaces:**
- Consumes: Phase 1 `Opening`, `Job`, `db.utcnow`, and PostgreSQL test-session fixture.
- Produces:
  - `Opening.application_email: str | None = None`, initially unset and populated only by Task 7's explicit apply-email extraction.
  - `RawOpening.application_email: str | None = None`; persist the field in `openings.insert_opening`.
  - `Application`, unique per `opening_id`, with `lane` in `auto_apply | review | manual_assist | rejected`; nullable `score` 0–100; JSONB `reasons` and `red_flags`; `status` in `awaiting_review | ready | manual_assist | rejected | blocked | dry_run | submitting | submitted | expired`; nullable `review_expires_at`, `submitted_at`, and sanitized `last_error`; `dry_run`; timezone-aware `created_at`/`updated_at`.
  - `ApplicationAnswer`: `application_id`, `question_key`, `source` (`fact | llm | unresolved`), `status` (`answered | blocked`), and `created_at`. Store answer text only in the MinIO answer artifact, never in PostgreSQL rows or events.
  - `ApplicationArtifact`: `application_id`, `kind`, `object_key`, `content_type`, `sha256`, and `created_at`.
  - `ApplicationEvent`: `application_id`, `event_type`, sanitized JSONB `details`, and `created_at`. Never put answer text, credentials, or full payloads in event details.
  - `ConnectorHealth`: unique `connector`, `status` (`healthy | degraded | unavailable`), `checked_at`, nullable `last_success_at`, and sanitized `detail`.
  - `upsert_application(session, opening_id, *, lane, status, score, reasons, red_flags, review_expires_at=None) -> Application`; an existing submitted application is immutable to matching reruns.
  - `transition_application(session, application, *, lane, status, event_type, details=None) -> Application`; reject invalid transitions and append one event atomically.
  - `get_application(session, application_id) -> Application | None` and `list_applications(session, *, lane=None, status=None, limit=100, offset=0) -> list[Application]`.

- [ ] **Step 1: Write failing repository tests** for one application per opening, JSON decision fields, explicit `application_email` persistence, atomic status/event updates, invalid transition rejection, answer/artifact/health foreign-key relationships, and absence of answer-text columns from the database model.
- [ ] **Step 2: Run `pytest tests/integration/test_applications.py -v`** and verify it fails because the Phase 2 models/repository do not exist.
- [ ] **Step 3: Implement the SQLModel tables, migration `0003_phase_2_workflow`, and repository functions** with PostgreSQL JSONB and timezone-aware timestamps.
- [ ] **Step 4: Run `pytest tests/integration/test_applications.py -v`** and verify all tests pass, including a duplicate `opening_id` constraint test.
- [ ] **Step 5: Run the full suite, Ruff lint, and the required formatter check; commit** as `feat: add application workflow persistence`.

### Task 2: MinIO artifact storage

**Files:**
- Create: `apps/api/lookout/artifacts.py`, `tests/unit/test_artifacts.py`
- Modify: `pyproject.toml`, `apps/api/lookout/config.py`, `.env.example`, `docker-compose.yml`
- Test: `tests/unit/test_artifacts.py`

**Interfaces:**
- Consumes: `ApplicationArtifact` from Task 1 and Phase 1 local PDF generation.
- Produces:
  - `ArtifactStore` protocol with `put_file(*, key: str, path: Path, content_type: str) -> str`, `get_bytes(key: str) -> bytes`, and `delete(key: str) -> None`.
  - `S3ArtifactStore(*, endpoint_url, bucket, access_key, secret_key, region="us-east-1")`, implemented with Boto3 `upload_file` (`ExtraArgs.ContentType`), `get_object`/`Body.read()`, and `delete_object`; configure `endpoint_url` and `Config(s3={"addressing_style": "path"})` for MinIO.
  - Generate opaque object keys as `applications/{application_id}/{artifact_id}/{kind}`; never include company, title, email, or other personal data in the key.
  - Settings for MinIO endpoint, bucket (`lookout-artifacts`), access key, and secret key. Configure an internal-only Compose service, persistent volume, health check, and idempotent bucket initialization; do not expose the MinIO console by default.

- [ ] **Step 1: Write failing tests** using a stubbed S3 client for binary upload/download, missing-object errors, and delete behavior; assert object keys contain no PII.
- [ ] **Step 2: Run `pytest tests/unit/test_artifacts.py -v`** and verify it fails because the artifact store is absent.
- [ ] **Step 3: Implement `ArtifactStore` and `S3ArtifactStore`**, then add Boto3 and MinIO Compose configuration. Store tailored PDFs, approved answers, and short per-opening records as separate objects; keep only object metadata in PostgreSQL.
- [ ] **Step 4: Run the unit test and a MinIO round-trip smoke test** (`put_file` → `get_bytes` → compare exact bytes); verify a restarted MinIO container retains the object.
- [ ] **Step 5: Run the full suite, Ruff lint, and formatter check; commit** as `feat: store application artifacts in minio`.

### Task 3: Match profile, deterministic filter, and LLM scoring

**Files:**
- Create: `apps/api/lookout/match_profile.py`, `apps/api/lookout/matching.py`, `config/matching.yml`, `templates/match-profile.yml`, `tests/unit/test_matching.py`, `tests/fixtures/matching/`
- Modify: `apps/api/lookout/config.py`, `.env.example`
- Test: `tests/unit/test_matching.py`

**Interfaces:**
- Consumes: `Opening`, `OpenRouterClient.complete_json`, `redact`, `contains_pii`, and `KnowledgeBase.identity`.
- Produces:
  - `MatchProfile` with `ideal_job: str`, `include_keywords: list[str]`, `exclude_keywords: list[str]`, `allowed_languages: list[str]`, `allowed_locations: list[str]`, `allowed_work_modes: list[str]`, `minimum_seniority: str | None`, `minimum_salary: float | None`, and `salary_currency: str | None`.
  - Validate `minimum_seniority` against `intern | junior | mid | senior | staff | principal` when set.
  - `load_match_profile(path: Path) -> MatchProfile`; the personal copy is `data/match-profile.yml`, copied from the fictional template and never committed.
  - `MatchingPolicy` from `config/matching.yml`: `auto_apply_min_score=90`, `review_min_score=70`; reject below 70. Validate `0 <= review_min_score < auto_apply_min_score <= 100`.
  - Add `Settings.match_profile_path`, `Settings.matching_policy_path`, and required non-empty `Settings.openrouter_scoring_model`, mapped to `MATCH_PROFILE_PATH`, `MATCHING_POLICY_PATH`, and `OPENROUTER_SCORING_MODEL`. Do not hardcode a model ID; scoring fails explicitly when the setting is missing.
  - `FilterResult(eligible: bool, reason: str | None)` and `SalaryRange(minimum: float | None, maximum: float | None, currency: str | None)`.
  - `deterministic_filter(opening: Opening, profile: MatchProfile) -> FilterResult`: any excluded keyword rejects; if include keywords are configured, at least one must match; explicit location/language/work-mode conflicts reject. A fixed seniority regex recognizes `intern < junior < mid < senior < staff < principal`; reject a recognized posting level below `minimum_seniority`, but do not reject an unclassified level. Missing salary or unknown work mode alone does not reject. `extract_salary(raw) -> SalaryRange | None` reads structured snake-case (`salary_min`, `salary_max`, `salary_currency`) and camel-case (`salaryMin`, `salaryMax`, `salaryCurrency`) keys only; reject below the configured minimum only when a range and matching currency are present.
  - `MatchDecision` with `score: int | None`, `reasons: list[str]`, `red_flags: list[str]`, `lane: Literal["auto_apply", "review", "manual_assist", "rejected"]`, and nullable `rejected_reason`.
  - `evaluate_opening(opening, profile, policy, *, llm, pii) -> MatchDecision`: deterministic rejects make no LLM call; otherwise request JSON `{score: 0..100, reasons: string[], red_flags: string[]}` using the OpenRouter scoring model. Redact the full prompt and assert no PII remains before calling the LLM.
  - Lane assignment: below 70 or deterministic reject → `rejected`; score ≥90 on Greenhouse/Lever or an opening with an explicit application email → `auto_apply`; score 70–89 on those targets → `review`; score ≥70 on every other target → `manual_assist`. LinkedIn alert openings are never treated as automatable.

- [ ] **Step 1: Write failing tests** for each deterministic rule, seniority regex and level ordering, missing salary, currency mismatch, invalid policy order, no LLM call on rejection, score-band routing, malformed/out-of-range JSON, and PII redaction in the complete scoring prompt.
- [ ] **Step 2: Run `pytest tests/unit/test_matching.py -v`** and verify it fails because the profile and matcher modules do not exist.
- [ ] **Step 3: Implement the profile loader, policy validation, deterministic filter, scoring prompt/schema validation, and lane classifier**; use the existing OpenRouter JSON client rather than introducing a second client.
- [ ] **Step 4: Run `pytest tests/unit/test_matching.py -v`** and verify all cases pass with fake LLM responses and fictional profile data.
- [ ] **Step 5: Run the full suite, Ruff lint, and formatter check; commit** as `feat: add deterministic and llm job matching`.

### Task 4: Persist lanes, review decisions, and expiry

**Files:**
- Create: `tests/unit/test_routing.py`, `tests/integration/test_review_queue.py`
- Create or modify: `apps/api/lookout/routing.py`, `apps/api/lookout/applications.py`
- Test: `tests/unit/test_routing.py`, `tests/integration/test_review_queue.py`

**Interfaces:**
- Consumes: `MatchDecision` from Task 3 and repository transitions from Task 1.
- Produces:
  - `persist_decision(session, opening, decision, *, now=None) -> Application`; create the initial status from the lane (`awaiting_review`, `ready`, `manual_assist`, or `rejected`), and set `review_expires_at = now + timedelta(days=7)` only for review.
  - `approve_review(session, application_id) -> Application`: only `review/awaiting_review` may transition to `auto_apply/ready`.
  - `decline_review(session, application_id) -> Application`: transition to `manual_assist/manual_assist`.
  - `expire_reviews(session, *, now=None) -> int`: review items at or past the seven-day TTL transition to `manual_assist/expired`; preserve the source URL through the related `Opening`.
  - A submitted decision cannot be reset, re-enqueued for application, or re-applied by rerunning matching.

- [ ] **Step 1: Write failing tests** for every lane's initial status, seven-day expiry boundary, approve/decline behavior, attempts to approve a non-review item, and rerunning a submitted opening.
- [ ] **Step 2: Run the two routing test files** and verify they fail because the routing transitions are absent.
- [ ] **Step 3: Implement `routing.py` and the allowed transition rules** using the transactional repository from Task 1; record sanitized events for every decision and review action.
- [ ] **Step 4: Run the routing unit and PostgreSQL integration tests** and verify all transitions and the TTL boundary pass.
- [ ] **Step 5: Run the full suite, Ruff lint, and formatter check; commit** as `feat: add review and application lane routing`.

### Task 5: Approved facts table and screener

**Files:**
- Create: `apps/api/lookout/facts.py`, `apps/api/lookout/screener.py`, `templates/facts.yml`, `tests/unit/test_screener.py`, `tests/fixtures/facts/`
- Modify: `apps/api/lookout/applications.py`, `apps/api/lookout/config.py`, `.env.example`
- Test: `tests/unit/test_screener.py`

**Interfaces:**
- Consumes: `ApplicationAnswer`, the knowledge-base loader, PII redaction, and the scoring/tailoring OpenRouter client interface.
- Produces:
  - `Settings.facts_path` defaulting to `data/facts.yml`; `ApprovedFacts` loaded by `load_facts(path: Path) -> ApprovedFacts` from local-only `data/facts.yml`; each value has an explicit key, value, and optional allowed values. Missing or malformed required files raise `FactsError`.
  - `FormQuestion(key, label, required, options=(), disqualifying=False)` and `ResolvedAnswer(key, answer, source, status)` where source is `fact | llm | unresolved` and status is `answered | blocked`.
  - `QuestionClass = Literal["work_authorization", "sponsorship", "salary", "start_date", "relocation", "location", "experience_years", "motivation", "relevant_experience"]`; `classify_question(question: FormQuestion) -> QuestionClass | None` uses deterministic case-insensitive label aliases for these classes; unknown labels return `None` rather than asking the LLM to classify them.
  - `resolve_question(question, facts, kb, *, llm, pii) -> ResolvedAnswer`: factual classes (`work_authorization`, `sponsorship`, `salary`, `start_date`, `relocation`, `location`, `experience_years`) use exact approved facts only. The only inferable classes are `motivation` and `relevant_experience`, grounded in KB facts and redacted before the LLM call. Any disqualifying question requires an exact approved fact and is never inferred. Unknown required or missing disqualifying facts return `blocked`; optional unknown questions remain unanswered.
  - `screen_questions(session, application, questions, *, facts, kb, llm, pii) -> list[ResolvedAnswer]`; persist only question/source/status metadata in PostgreSQL and return answer text in memory for the worker to write to MinIO. Return blockers without submitting anything.

- [ ] **Step 1: Write failing tests** for label classification (`Are you legally authorized to work?` → `work_authorization`; `Will you require visa sponsorship?` → `sponsorship`; `What are your salary expectations?` → `salary`; `When can you start?` → `start_date`; `Are you willing to relocate?` → `relocation`; `Where are you located?` → `location`; `How many years of Python experience?` → `experience_years`; `Why are you interested in this role?` → `motivation`; `Describe your relevant experience` → `relevant_experience`), exact fact mapping, allowed-value validation, missing/disqualifying facts, unknown required versus optional questions, and PII-free inference prompts.
- [ ] **Step 2: Run `pytest tests/unit/test_screener.py -v`** and verify it fails because the facts and screener modules do not exist.
- [ ] **Step 3: Implement the local facts loader and enumerated question policy**; do not add free-form inference for factual or disqualifying questions.
- [ ] **Step 4: Run `pytest tests/unit/test_screener.py -v`** and verify all cases pass with fictional facts and fake LLM responses.
- [ ] **Step 5: Run the full suite, Ruff lint, and formatter check; commit** as `feat: add facts-gated application screening`.

### Task 6: Infisical secrets, persistent sessions, and connector health

**Files:**
- Create: `apps/api/lookout/secrets.py`, `apps/api/lookout/browser_sessions.py`, `apps/api/lookout/connector_health.py`, `tests/unit/test_secrets.py`, `tests/unit/test_browser_sessions.py`, `tests/unit/test_connector_health.py`
- Create: `docker/postgres/init/create_infisical_database.sql`
- Modify: `pyproject.toml`, `apps/api/lookout/config.py`, `.env.example`, `docker-compose.yml`, `apps/api/Dockerfile`, `apps/worker/Dockerfile`, `README.md`
- Test: the three test files above

**Interfaces:**
- Consumes: Task 1 `ConnectorHealth`, the existing Compose PostgreSQL service, and Playwright Python.
- Produces:
  - An Infisical service using the existing PostgreSQL service with a separate Infisical database, persistent storage, and a release-pinned image; create the database idempotently for fresh volumes and document a non-destructive one-time `createdb` for existing Phase 1 volumes. Configure the required internal Redis only for Infisical, never for the Lookout job queue. Generate non-default encryption/auth secrets; do not place sample values in `.env.example`.
  - `SecretProvider.get_secret(name: str, *, path: str) -> str`; `InfisicalSecretProvider` creates `InfisicalSDKClient(host=...)`, calls `client.auth.universal_auth.login(client_id=..., client_secret=...)`, then `client.secrets.get_secret_by_name(name, environment_slug, path, project_id=...)`. Missing secrets and service outages raise a sanitized `SecretProviderError`; never log returned values.
  - `Settings.dry_run=True` and `Settings.auto_submit_enabled=False`; both must be explicitly changed before any connector can submit.
  - SMTP host, port, sender address, and Infisical secret name/path are configuration values; SMTP password is retrieved only from Infisical.
  - Settings for Infisical URL, Universal Auth client ID/secret, project ID, environment slug, and secret path. The bootstrap identity values stay in local `.env`; SMTP/platform secrets live in Infisical.
  - Map these values to `INFISICAL_URL`, `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET`, `INFISICAL_PROJECT_ID`, and `INFISICAL_ENVIRONMENT` (default `dev`). Map `DRY_RUN=true` and `AUTO_SUBMIT_ENABLED=false` to the fail-closed submission settings.
  - Exact SMTP settings are `SMTP_HOST`, `SMTP_PORT`, and `SMTP_FROM`; retrieve `SMTP_PASSWORD` from Infisical path `/application`. Bootstrap a local Infisical project/environment and a read-only machine identity, with the steps documented in `README.md`.
  - `BrowserSessionManager.open(platform: Literal["greenhouse", "lever"], *, headless: bool) -> ContextManager[BrowserContext]`, backed by the synchronous `launch_persistent_context(data/browser-profiles/<platform>)`. Hold a cross-process lock for the profile while yielded; close the context and release the lock on exit. Browser profiles are gitignored and never stored in MinIO.
  - `ConnectorHealthSnapshot(connector, status, detail, last_success_at)` with status `healthy | degraded | unavailable`.
  - `check_connector_health(platform: Literal["greenhouse", "lever", "email"], *, settings: Settings, secrets: SecretProvider, sessions: BrowserSessionManager) -> ConnectorHealthSnapshot`; `save_connector_health(session, snapshot, *, now=None) -> ConnectorHealth` upserts the per-connector record. A daily worker check records a sanitized reason. Expose machine-readable health for Phase 3 UI alerts.
  - Bind the host API and Infisical ports to `127.0.0.1` by default. Document local generation of non-default Infisical encryption/auth secrets. Users must manually bootstrap browser SSO/password sessions; CAPTCHA/2FA is not bypassed.

- [ ] **Step 1: Write failing tests** for Infisical secret retrieval/error sanitization, persistent per-platform profile selection, rejection of simultaneous use of one profile, context cleanup, and daily health result persistence without secret values.
- [ ] **Step 2: Run the three unit test files** and verify they fail because the secret/session/health modules are absent.
- [ ] **Step 3: Implement the secret provider, Compose services, persistent browser-session manager, and daily health checks**; pin Infisical to a specific release tag and keep the Lookout queue PostgreSQL-backed.
- [ ] **Step 4: Run the unit tests and a Compose health smoke test** with fake secrets; verify the Infisical, API, worker, and PostgreSQL services become healthy and no secret appears in logs.
- [ ] **Step 5: Run the full suite, Ruff lint, and formatter check; commit** as `feat: add connector secrets and session health`.

### Task 7: Greenhouse, Lever, and explicit email appliers

**Files:**
- Create: `apps/api/lookout/appliers/__init__.py`, `apps/api/lookout/appliers/base.py`, `greenhouse.py`, `lever.py`, `email.py`, `tests/unit/appliers/`, `tests/fixtures/appliers/`
- Modify: relevant collector parsers
- Test: `tests/unit/appliers/` and collector parser tests

**Interfaces:**
- Consumes: `BrowserSessionManager`, `SecretProvider`, `FormQuestion`, `ResolvedAnswer`, MinIO artifacts, and the existing `Opening`/`RawOpening` types.
- Produces:
  - Populate `RawOpening.application_email` only from an explicit apply-email field or `mailto:` application link in the source payload; do not treat arbitrary recruiter/contact addresses as an application target. Task 1 already defines and persists the nullable field.
  - `ApplicationForm(fields: list[FormQuestion])`, `ApplyResult(status: Literal["submitted", "dry_run", "manual_assist"], detail: str)`, and `Applier` protocol with `inspect(opening, *, resume_path: Path) -> ApplicationForm` and `submit(application: Application, opening: Opening, *, resume_path: Path, answers: list[ResolvedAnswer], dry_run: bool, auto_submit_enabled: bool) -> ApplyResult`. `detail` is sanitized. `submit` must verify `application.lane == "auto_apply"`, `application.status == "submitting"`, and both explicit submit flags before a final side effect.
  - `GreenhouseApplier` and `LeverApplier` use local Playwright pages/forms; `EmailApplier` sends only to `opening.application_email`, attaches the tailored PDF, and uses SMTP configuration plus `SMTP_PASSWORD` from Infisical path `/application`. Build the subject as `Application — {opening.title}` and use a short deterministic body in the posting's detected language. No unaddressed email or follow-up messages.
  - Both browser adapters inspect and fill supported fields in dry-run but never click the final submit control. Unsupported required controls, missing explicit email target, expired login, CAPTCHA, or 2FA return `manual_assist` with a sanitized reason.
  - A real submit requires `dry_run=False`, `AUTO_SUBMIT_ENABLED=true`, lane `auto_apply`, and status `submitting` committed before the external side effect. Once status is `submitting`, an ambiguous result or worker crash must downgrade to manual-assist; never replay the submit automatically.

- [ ] **Step 1: Write failing tests** with local fictional Greenhouse/Lever HTML and a fake SMTP transport for field inspection, supported field fill, unsupported required questions, explicit email target only, dry-run never submitting/sending, and submit ambiguity.
- [ ] **Step 2: Run `pytest tests/unit/appliers tests/unit/collectors -v`** and verify it fails because the application adapters and apply-email normalization are absent.
- [ ] **Step 3: Implement the common protocol and three connectors**; add only explicit application-email extraction and use the persistent session manager for browser adapters.
- [ ] **Step 4: Run the applier and collector tests** and verify dry-run does not invoke a final submit or SMTP send, while supported fictional forms yield the expected answers.
- [ ] **Step 5: Run the full suite, Ruff lint, and formatter check; commit** as `feat: add greenhouse lever and email appliers`.

### Task 8: Queue orchestration, API/CLI review, and scheduling

**Files:**
- Modify: `apps/api/lookout/ingest.py`, `worker.py`, `api.py`, `cli.py`, `README.md`
- Create: `tests/unit/test_workflow_worker.py`, `tests/unit/test_review_api.py`, `tests/unit/test_workflow_cli.py`, `tests/integration/test_automation_loop.py`
- Test: the four test files above

**Interfaces:**
- Consumes: all prior task interfaces and Phase 1 collection/tailoring handlers.
- Produces:
  - New jobs `match` and `apply`; add inserted opening IDs to `IngestStats` so the worker enqueues matching for new openings. Add `lookout match --backfill` to enqueue unprocessed existing openings without overwriting submitted records.
  - Worker matching loads the local profile/policy, evaluates each opening, persists the decision, then enqueues preparation only for `auto_apply`, `review`, and `manual_assist`. Rejected openings are retained as decisions but are not tailored.
  - Every eligible lane is tailored and its PDF stored in MinIO before handoff: review waits with its PDF for approval; manual-assist receives its PDF without automated form filling; auto-apply (and an approved review) inspects/screens questions before applying. Any unresolved required/disqualifying question transitions to `manual_assist/blocked` and stops submission. Store resolved answer text only as an answer artifact before submission and keep a short sanitized per-opening record in MinIO. Rejected openings are not tailored.
  - Application handler honors both fail-closed submission settings, checks application state immediately before submission, writes `submitting` before external I/O, stores the final result/event, and never resubmits a `submitted` or ambiguous `submitting` record.
  - APScheduler expires review items at least hourly and checks connector health daily; one connector's failure must not stop other sources or worker polling.
  - API: `GET /applications?lane&status&limit&offset` and `GET /applications/{id}` include the related opening's company, title, and source URL; `POST /applications/{id}/approve`, `POST /applications/{id}/decline`, `GET /applications/{id}/artifacts` (metadata), `GET /artifacts/{artifact_id}` (stream object bytes through the API), and `GET /connectors/health`. Invalid transitions return 409, unknown IDs return 404.
  - CLI: `list-applications`, `approve APPLICATION_ID`, `decline APPLICATION_ID`, `match [--backfill]`, `browser-auth PLATFORM`, and `check-connectors`. Keep Phase 1 `collect`, `tailor`, and `list-openings` commands working.
  - Use the match-profile/policy/scoring, facts, MinIO, SMTP, and Infisical settings created in Tasks 2–6; do not duplicate configuration definitions.

- [ ] **Step 1: Write failing tests** for collection-to-match enqueueing, backfill idempotency, complete lane-specific worker handling, review endpoints, 404/409 behavior, worker continuation after connector failure, and no duplicate submission after stale-job recovery.
- [ ] **Step 2: Run the four targeted test files** and verify they fail because Phase 2 job handlers, endpoints, and commands are absent.
- [ ] **Step 3: Implement queue handlers, scheduler jobs, review/artifact/health endpoints, CLI commands, settings, and README instructions** using the interfaces from prior tasks.
- [ ] **Step 4: Run the targeted tests plus `tests/integration/test_automation_loop.py`** against PostgreSQL and MinIO; verify the full dry-run workflow creates a lane decision, tailored artifact, screening record, and no final submit.
- [ ] **Step 5: Run the full suite, Ruff lint, and formatter check; commit** as `feat: connect matching and application workflow`.

### Task 9: Phase 2 acceptance walkthrough

**Files:**
- Create: `docs/runbooks/phase-2-acceptance.md`
- Modify: `README.md` if the verified Phase 2 startup/operations commands need a concise update.

- [ ] **Step 1: Prepare fictional/local test data** from committed templates; verify `.env`, `data/`, browser profiles, and MinIO objects are ignored or local-only.
- [ ] **Step 2: Start the complete local stack** and verify PostgreSQL migrations, API, worker, MinIO bucket, Infisical, and health checks.
- [ ] **Step 3: Run matching and review flows** with fake LLM outputs and fictional openings; verify all four lanes, seven-day expiry, approval/decline, and re-run idempotency.
- [ ] **Step 4: Run the application flow in dry-run only** against local HTML fixtures, then manually inspect one authorized Greenhouse/Lever form without final submission if credentials are available. Do not submit a real application as part of acceptance.
- [ ] **Step 5: Verify artifacts and failure behavior**: download the PDF/answer record from MinIO, test missing secrets and expired sessions, and confirm logs/events contain no credentials, direct PII, or full answer payloads.
- [ ] **Step 6: Run final gates**: `docker compose exec api pytest -q`, `docker compose exec api ruff check .`, `docker compose exec api ruff format --check apps tests`, and `docker compose build api worker`; record exact results and skipped credential-dependent checks in the runbook.
- [ ] **Step 7: Commit** the verified acceptance record as `docs: record phase 2 acceptance results`.

---

## Self-Review Notes

- **Spec coverage:** PRD §4 lanes/dry-run/TTL → Tasks 3–4 and 7–8; §5.2 matcher and bands → Task 3; §5.3 PostgreSQL applications, audit, and MinIO artifacts → Tasks 1–2; §5.4 existing factual resume guardrail → Tasks 2 and 8; §5.5 approved facts and impediment handling → Task 5; §5.6 Greenhouse/Lever/email submission and failure downgrade → Tasks 6–8; §5.7 vault/session/health backend → Task 6, with its credential-management UI remaining Phase 3; §6 PII boundary → Tasks 3 and 5; §7 no frontend in Phase 2 → all tasks keep UI out of scope.
- **Spec call:** PRD §5.7 calls for Infisical and §11 plans it as a dedicated service; Task 6 includes Infisical. Its required internal Redis is explicitly isolated from Lookout's PostgreSQL job queue. The web credential-management UI remains Phase 3.
- **Defaults chosen where the PRD leaves values open:** use `90` for auto-apply and `70` for review as conservative initial thresholds in `config/matching.yml`; expose the values for local adjustment and later Phase 3 UI configuration. Missing salary or unknown work mode alone does not reject an opening.
- **Type consistency:** `Application`, `ApplicationAnswer`, `ApplicationArtifact`, `ApplicationEvent`, `ConnectorHealth`, `MatchProfile`, `MatchDecision`, `FormQuestion`, `ResolvedAnswer`, `ApplicationForm`, `ApplyResult`, `ArtifactStore`, `SecretProvider`, and `Applier` are defined once above and reused by later tasks.
- **Safety:** Phase 2 acceptance never performs a real final submit. Real submission requires two explicit settings, an eligible lane/approval, an explicit application destination, and a persisted pre-submit state.
