# Phase 1 — MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 MVP from the PRD: Collector (Tier 0 + Tier 1 + LinkedIn email alerts) + State DB + Resume Tailor prototype (knowledge base → tailored PDF), manually triggered, no frontend (PRD §7).

**Architecture:** Monorepo (S9) with a single Python package `lookout` under `apps/api/` (FastAPI + agent modules) and a thin `apps/worker/` container running the same package's worker entrypoint. PostgreSQL is the state DB (openings + DB-backed `jobs` queue); a dedicated worker process runs APScheduler and executes jobs. Connectors are split into a thin HTTP transport (`fetch`, untested) and pure parsers (`parse_*`, fixture-tested). The tailor pipeline loads the Markdown knowledge base, redacts PII, calls OpenRouter (tailoring slot), validates the output against the KB, and renders Jinja2 HTML → WeasyPrint PDF to a local artifacts dir. All services run locally via Docker Compose; tests execute inside the `api` container (WeasyPrint needs system Pango libraries that are painful on Windows hosts).

**Tech Stack:** Python 3.12 (≥3.11 floor), FastAPI, SQLModel + Alembic, PostgreSQL 16, APScheduler 3, httpx, feedparser, rapidfuzz, Jinja2, WeasyPrint, pydantic-settings, google-api-python-client + google-auth-oauthlib, pytest + ruff, Docker Compose.

**Spec:** `docs/PRD.md` (frozen requirements Q1–Q16, F1–F10, stack round S). This plan implements **only** PRD §7 Phase 1.

## Global Constraints

Every task implicitly includes these (values copied from the PRD/rules):

- Python ≥ 3.11 (containers pin 3.12); monorepo layout per S9: `apps/api`, `apps/worker`, `apps/web` (untouched, Phase 3), `docker-compose.yml` at root.
- **PostgreSQL from day one** (S7) + SQLModel + Alembic migrations. No SQLite in app code.
- Queue: **DB-backed `jobs` table in Postgres + dedicated worker process**; scheduling via APScheduler (S2). No Redis.
- PDF: **Jinja2 HTML/CSS → WeasyPrint** (S4).
- LLM: **OpenRouter** gateway (S5); tailoring slot = Claude Haiku class. Only LLM inference leaves the machine (F1). Scoring slot is Phase 2 — do not build it.
- **Direct PII (name, CPF, phone, address) NEVER sent to external LLMs** (Q14, F6); a redaction layer runs before every LLM call. Company names are allowed (F6).
- Dedup at ingestion (F4): key = normalized (company + title); similarity via **rapidfuzz** (S8). Duplicates never enter the DB.
- LinkedIn is **email-alerts only** (Q4): Gmail API, OAuth read-only scope `https://www.googleapis.com/auth/gmail.readonly` (S6). No LinkedIn scraping.
- Resume Tailor: selects/rewrites **only facts present in the knowledge base, never invents** (Q12); output PDF, language follows the posting (PT-BR/EN), ATS-friendly (single-column, standard headings, real text).
- Everything local via **Docker Compose** (F1). Phase 1 services: `postgres`, `api`, `worker` only — `minio`/`infisical`/`web` land in later phases (PRD §7); secrets come from `.env` (privacy rule).
- Tests: `pytest`; lint/format: `ruff check` / `ruff format`. Fixtures use **fictional/anonymized data only** (privacy rule). `data/` is gitignored and never committed.
- All code, comments, docs and commit messages in **English**; Conventional Commits.
- Scope: **no matcher, no lanes, no applier, no screener, no frontend, no Tier 2 sources** (PRD §7).

## Review Focus

The five failure modes most likely to bite, each pinned to a test in the owning task:

1. **Fuzzy dedup merges distinct openings** at the same company ("Backend Engineer" vs "Senior Backend Engineer" at Acme), silently losing real jobs — expected behavior: near-identical re-posts dedup, genuinely different roles don't. → Task 4 (`test_is_duplicate_keeps_distinct_roles_at_same_company`), Task 5.
2. **PII hides in KB free text** (a phone number inside an experience description, not frontmatter) and leaks to OpenRouter — expected behavior: redaction scans full text, and the pipeline asserts no PII remains before the call. → Task 12 (`test_redact_catches_pii_inside_free_text`), Task 14 (FakeLLM assertion).
3. **One source breaking** (HTTP 500, schema change) aborts the whole collection run or kills the worker — expected behavior: per-source isolation, error recorded, other sources still ingested, worker keeps polling. → Task 5 (`test_collect_all_isolates_failing_source`), Task 15.
4. **LLM fabricates resume content** (unknown KB id, invented skill) and a fabricated PDF is produced — expected behavior: validation rejects, error raised, no PDF written (R1, F2). → Task 13 (`test_validation_flags_fabricated_facts`), Task 14.
5. **Worker crash mid-job** loses or double-processes jobs — expected behavior: concurrent claimants get distinct jobs (`FOR UPDATE SKIP LOCKED`); stale `running` jobs return to `pending`. → Task 3 (`test_claim_next_skips_locked_rows`, `test_reap_stale_returns_crashed_jobs_to_pending`).

## File Structure

```
apps/
├── api/
│   ├── Dockerfile                  # python:3.12-slim + Pango libs, pip install -e ".[dev]"
│   └── lookout/                    # the single Python package (FastAPI + agent modules)
│       ├── __init__.py
│       ├── config.py               # Settings (pydantic-settings) + get_settings()
│       ├── db.py                   # engine/session helpers, utcnow()
│       ├── models.py               # Opening, Job (SQLModel tables)
│       ├── openings.py             # openings repository
│       ├── queue.py                # jobs queue operations
│       ├── normalize.py            # text/company/title normalization
│       ├── dedup.py                # rapidfuzz duplicate detection
│       ├── ingest.py               # fetch → validate → dedup → insert pipeline
│       ├── redaction.py            # PII redaction
│       ├── kb.py                   # knowledge base loader (Markdown + frontmatter)
│       ├── llm.py                  # OpenRouter client
│       ├── collectors/
│       │   ├── base.py             # RawOpening, Collector protocol, CollectorError
│       │   ├── registry.py         # build_collectors / get_collector
│       │   ├── remoteok.py  remotive.py  arbeitnow.py  jobicy.py
│       │   ├── weworkremotely.py  workingnomads.py  himalayas.py
│       │   ├── adzuna.py  hn_whoishiring.py
│       │   ├── greenhouse.py  lever.py  workable.py
│       │   └── linkedin_email.py
│       ├── tailor/
│       │   ├── schema.py           # TailoredResume (pydantic)
│       │   ├── prompts.py          # prompt construction
│       │   ├── validation.py       # KB-only guardrail check
│       │   ├── render.py           # Jinja2 HTML rendering
│       │   ├── pdf.py              # WeasyPrint
│       │   └── pipeline.py         # tailor_resume orchestration
│       ├── api.py                  # FastAPI app factory
│       ├── worker.py               # APScheduler + queue poll entrypoint
│       └── cli.py                  # python -m lookout.cli
├── worker/Dockerfile               # same base image; CMD python -m lookout.worker
└── web/                            # Phase 3 — only a .gitkeep
alembic/  alembic.ini               # migrations (repo root)
config/sources.yml                  # per-source enable/interval/config
templates/kb/                       # fictional starter KB (user copies to data/kb)
templates/resume/base.html  resume.css
tests/{conftest.py, unit/, integration/, fixtures/}
docker-compose.yml  pyproject.toml  .env.example  .dockerignore
```

---

### Task 1: Project scaffolding, tooling and Docker Compose skeleton

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.dockerignore`, `docker-compose.yml`, `apps/api/Dockerfile`, `apps/worker/Dockerfile`, `apps/web/.gitkeep`, `apps/api/lookout/__init__.py`, `apps/api/lookout/config.py`, `apps/api/lookout/api.py`, `apps/api/lookout/worker.py`, `tests/__init__.py`, `tests/unit/test_health.py`
- Modify: `.opencode/rules/stack.md` (replace provisional content with the frozen stack from PRD §11: Python + FastAPI, PostgreSQL + SQLModel + Alembic, DB-backed queue + APScheduler, Playwright (Phase 2), WeasyPrint, OpenRouter, Gmail API, rapidfuzz, Infisical (later phase), Docker Compose; pytest/ruff tooling unchanged)
- Test: `tests/unit/test_health.py`

**Interfaces:**
- Produces: `Settings` in `lookout/config.py` — a `pydantic_settings.BaseSettings` with fields: `database_url: str = "postgresql+psycopg://lookout:lookout@postgres:5432/lookout"`, `openrouter_api_key: str = ""`, `openrouter_tailoring_model: str = "anthropic/claude-3.5-haiku"`, `adzuna_app_id: str = ""`, `adzuna_app_key: str = ""`, `gmail_credentials_file: Path = Path("data/gmail_credentials.json")`, `gmail_token_file: Path = Path("data/gmail_token.json")`, `gmail_label: str = "lookout/jobs"`, `kb_path: Path = Path("data/kb")`, `artifacts_dir: Path = Path("data/artifacts")`, `sources_config: Path = Path("config/sources.yml")`, `worker_poll_seconds: int = 5`, `dedup_company_threshold: float = 90.0`, `dedup_title_threshold: float = 90.0`; plus `get_settings() -> Settings` (`functools.lru_cache`). `create_app() -> FastAPI` in `lookout/api.py` with `GET /health -> {"status": "ok"}`.

- [x] **Step 1: Write the failing smoke test**

```python
# tests/unit/test_health.py
from lookout.api import create_app
from fastapi.testclient import TestClient

def test_health():
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok"}
```

- [x] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_health.py -v` (inside container once built; fails locally with `ModuleNotFoundError` before that — acceptable, note it).

- [x] **Step 3: Create the scaffold**

`pyproject.toml`: `[project]` name `lookout`, `requires-python = ">=3.11"`, dependencies: `fastapi`, `uvicorn[standard]`, `sqlmodel`, `alembic`, `psycopg[binary]`, `apscheduler>=3.10,<4`, `httpx`, `pydantic-settings`, `jinja2`, `weasyprint`, `rapidfuzz`, `feedparser`, `python-frontmatter`, `pyyaml`, `google-api-python-client`, `google-auth-oauthlib`; `[project.optional-dependencies] dev = ["pytest", "ruff", "pypdf"]`; `[tool.hatch.build.targets.wheel] packages = ["apps/api/lookout"]`; `[tool.ruff] line-length = 100, target-version = "py311"`; `[tool.pytest.ini_options] testpaths = ["tests"]`. `config.py` with `Settings`/`get_settings()` as above. `api.py` with `create_app()` (health route only). `worker.py` with `main()` that logs "worker started" and sleeps in a loop. Dockerfiles: `FROM python:3.12-slim`, `apt-get install -y --no-install-recommends libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev`, `WORKDIR /app`, copy `pyproject.toml` + `apps/api/lookout`, `pip install --no-cache-dir -e ".[dev]"`; api CMD runs alembic then uvicorn (alembic not present yet — for this task the CMD is `sh -c "uvicorn lookout.api:create_app --factory --host 0.0.0.0 --port 8000"`; Task 2 adds the alembic prefix), worker CMD `python -m lookout.worker`. `docker-compose.yml` as in the architecture note: `postgres` (postgres:16-alpine, user/pass/db `lookout`, volume `pgdata`, healthcheck `pg_isready -U lookout`), `api` (build context `.`, dockerfile `apps/api/Dockerfile`, `env_file: .env`, volumes `.:/app` and `./data:/app/data`, port `8000:8000`, `depends_on: postgres: service_healthy`, healthcheck `python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"`), `worker` (same build pattern, dockerfile `apps/worker/Dockerfile`, no ports, `depends_on: api: service_healthy`). `.env.example` mirroring the `Settings` fields (with `DATABASE_URL=postgresql+psycopg://lookout:lookout@postgres:5432/lookout`). `.dockerignore`: `.git`, `.venv`, `data`, `**/__pycache__`, `.env`, `tests`. `config/sources.yml` created here with all 13 sources per the Global Constraints shape (Task 5 consumes it). Update `.opencode/rules/stack.md` as described above.

- [x] **Step 4: Build and verify green**

Run: `cp .env.example .env`; `docker compose up -d --build`; then `docker compose exec api pytest tests/unit/test_health.py -v` → PASS; `docker compose exec api ruff check .` → clean; `docker compose ps` → `postgres`, `api` healthy, `worker` running. (Prerequisite: Docker Desktop running.)

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "chore: scaffold monorepo, tooling and docker compose skeleton"
```

---

### Task 2: State DB — `Opening` model, Alembic, repository

**Files:**
- Create: `apps/api/lookout/db.py`, `apps/api/lookout/models.py`, `apps/api/lookout/openings.py`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_create_openings.py`, `tests/conftest.py`, `tests/integration/test_openings_repo.py`
- Modify: `apps/api/Dockerfile` CMD → `sh -c "alembic upgrade head && uvicorn lookout.api:create_app --factory --host 0.0.0.0 --port 8000"`
- Test: `tests/integration/test_openings_repo.py`

**Interfaces:**
- Produces:
  - `class Opening(SQLModel, table=True)` (`lookout/models.py`): `id: uuid.UUID` (default `uuid4`, PK), `source: str`, `external_id: str | None`, `company: str`, `title: str`, `location: str | None`, `url: str`, `description: str` (default `""`), `posted_at: datetime | None`, `collected_at: datetime`, `dedup_key: str` (indexed), `raw: dict` (JSONB, default `{}`); `UniqueConstraint("source", "external_id")`; all datetimes `DateTime(timezone=True)`.
  - `utcnow() -> datetime` (timezone-aware UTC) in `lookout/db.py`; `build_engine(settings: Settings) -> Engine`; `session_scope(settings) -> Iterator[Session]` (context manager, commits on success / rolls back on exception).
  - Repository in `lookout/openings.py`: `insert_opening(session: Session, raw: "RawOpening") -> Opening`; `get_opening(session: Session, opening_id: uuid.UUID) -> Opening | None`; `list_openings(session: Session, *, limit: int = 100, offset: int = 0) -> list[Opening]`; `list_dedup_keys(session: Session) -> list[str]`.
  - `tests/conftest.py`: session-scoped test database `lookout_test` created from `TEST_DATABASE_URL` (default derived from `DATABASE_URL` with `_test` suffix); **guard: raise if the test URL's database name does not end with `_test`**; per-test function-scoped `session` fixture with `metadata.drop_all`/`create_all` isolation.
- Consumes: `Settings` from Task 1. `RawOpening` from Task 5 (type hint only — use string annotation / `TYPE_CHECKING`; Task 5 makes it concrete).

- [x] **Step 1: Write the failing integration test**

```python
# tests/integration/test_openings_repo.py
def test_insert_and_get_opening(session):
    opening = insert_opening(session, make_raw_opening(company="Globex", title="Backend Engineer"))
    assert get_opening(session, opening.id).dedup_key == "globex|backend engineer"

def test_same_source_external_id_cannot_be_inserted_twice(session):
    raw = make_raw_opening(external_id="42")
    insert_opening(session, raw)
    with pytest.raises(IntegrityError):
        insert_opening(session, raw)
```
(`make_raw_opening` is a local test helper building the `RawOpening` dataclass — Task 5's interface; write the helper against the signature pinned there: `RawOpening(source, external_id, company, title, location, url, description, posted_at, raw)`.)

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/integration/test_openings_repo.py -v`
Expected: FAIL with `ModuleNotFoundError` (neither `lookout.models` nor `lookout.collectors.base` exists yet; either import error is acceptable — the helper import of `RawOpening` resolves when Task 5 lands, since the helper is written against the signature pinned there).

- [x] **Step 3: Implement models, db, repository, Alembic**

`alembic init alembic` shape at repo root; `alembic.ini` with `script_location = alembic`, `sqlalchemy.url` left empty; `alembic/env.py` reads `get_settings().database_url` and targets `SQLModel.metadata`. Models exactly as the Interfaces block. Migration `0001_create_openings` autogenerated then reviewed by hand. Repository functions as pinned.

- [x] **Step 4: Run to verify it passes**

Run: `docker compose up -d --build` (new api CMD), then `docker compose exec api alembic upgrade head`, then `docker compose exec api pytest tests/integration -v`
Expected: 2 PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add openings state database with alembic migrations" && git push origin HEAD
```

---

### Task 3: DB-backed job queue (`jobs` table + claim semantics)

**Files:**
- Create: `apps/api/lookout/queue.py`, `alembic/versions/0002_create_jobs.py`, `tests/integration/test_queue.py`
- Modify: `apps/api/lookout/models.py` (add `Job`)
- Test: `tests/integration/test_queue.py`

**Interfaces:**
- Consumes: `db.session_scope`, `db.utcnow`, `models` from Task 2.
- Produces:
  - `class Job(SQLModel, table=True)`: `id: uuid.UUID` (PK), `type: str`, `payload: dict` (JSONB), `status: str` (`"pending" | "running" | "done" | "failed"`, default `"pending"`, indexed), `run_at: datetime` (tz-aware, default `utcnow`), `attempts: int = 0`, `max_attempts: int = 3`, `last_error: str | None`, `created_at: datetime`, `updated_at: datetime`.
  - `enqueue(session: Session, job_type: str, payload: dict, *, run_at: datetime | None = None, max_attempts: int = 3) -> Job`
  - `claim_next(session: Session, *, now: datetime | None = None) -> Job | None` — oldest `pending` job with `run_at <= now`, selected `FOR UPDATE SKIP LOCKED`, transitions to `running`, increments `attempts`.
  - `complete(session: Session, job: Job) -> None`
  - `fail(session: Session, job: Job, error: str) -> None` — if `job.attempts >= job.max_attempts` → status `failed`; else back to `pending` with `run_at = now + timedelta(minutes=2 ** job.attempts)`; always sets `last_error`.
  - `reap_stale(session: Session, *, stale_after: timedelta = timedelta(minutes=30)) -> int` — `running` jobs with `updated_at` older than `stale_after` return to `pending`; returns count.

- [x] **Step 1: Write the failing tests**

```python
# tests/integration/test_queue.py
def test_claim_next_picks_oldest_due_job(session):
    enqueue(session, "collect", {"source": "later"}, run_at=utcnow() + timedelta(hours=1))
    first = enqueue(session, "collect", {"source": "now"})
    claimed = claim_next(session)
    assert claimed.id == first.id and claimed.status == "running" and claimed.attempts == 1
    assert claim_next(session) is None  # nothing else due

def test_claim_next_skips_locked_rows(session, engine):
    enqueue(session, "collect", {"source": "a"}); enqueue(session, "collect", {"source": "b"})
    with Session(engine) as tx2:
        assert claim_next(session).payload["source"] == "a"   # tx1 holds row lock (uncommitted)
        assert claim_next(tx2).payload["source"] == "b"        # tx2 skips the locked row

def test_fail_requeues_with_backoff_then_gives_up(session):
    job = enqueue(session, "collect", {"source": "x"}, max_attempts=2)
    claim_next(session); fail(session, job, "boom")
    assert job.status == "pending" and job.run_at > utcnow() and job.last_error == "boom"
    claim_next(session, now=utcnow() + timedelta(minutes=3)); fail(session, job, "boom again")
    assert job.status == "failed"

def test_reap_stale_returns_crashed_jobs_to_pending(session):
    job = enqueue(session, "collect", {"source": "x"})
    claim_next(session)
    job.updated_at = utcnow() - timedelta(hours=1); session.add(job); session.commit()
    assert reap_stale(session) == 1
    session.refresh(job); assert job.status == "pending"
```
(`engine` fixture: add to `tests/conftest.py`, reusing the test-DB engine.)

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/integration/test_queue.py -v`
Expected: FAIL (`lookout.queue` does not exist).

- [x] **Step 3: Implement `queue.py`, `Job` model and migration `0002_create_jobs`**

`claim_next`: `select(Job).where(status=="pending", run_at<=now).order_by(created_at).with_for_update(skip_locked=True).limit(1)`. Backoff exactly `2 ** attempts` minutes as pinned.

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api alembic upgrade head && docker compose exec api pytest tests/integration -v`
Expected: all PASS (Task 2 + Task 3).

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add db-backed job queue" && git push origin HEAD
```

---

### Task 4: Normalization and fuzzy dedup

**Files:**
- Create: `apps/api/lookout/normalize.py`, `apps/api/lookout/dedup.py`, `tests/unit/test_normalize.py`, `tests/unit/test_dedup.py`
- Test: `tests/unit/test_normalize.py`, `tests/unit/test_dedup.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `normalize_text(value: str) -> str` — NFKD, strip combining marks (accents), lowercase, replace punctuation with space, collapse whitespace.
  - `normalize_company(name: str) -> str` — `normalize_text` then drop trailing legal-suffix tokens: `{inc, incorporated, llc, ltd, ltda, corp, corporation, company, co, gmbh, sarl, sa}`.
  - `normalize_title(title: str) -> str` — `normalize_text` then drop tokens `{remote, hybrid, onsite}`.
  - `dedup_key(company: str, title: str) -> str` — `f"{normalize_company(company)}|{normalize_title(title)}"`.
  - `is_duplicate(candidate_key: str, existing_keys: Sequence[str], *, company_threshold: float = 90.0, title_threshold: float = 90.0) -> bool` — splits keys on `"|"`; duplicate when any existing key has `rapidfuzz.fuzz.token_set_ratio` on the **company** part ≥ `company_threshold` **and** `fuzz.token_sort_ratio` on the **title** part ≥ `title_threshold`. (token_set for company tolerates "Mercado Livre" ⊂ "Mercado Livre Brasil"; token_sort for title prevents "Backend Engineer" ⊂ "Senior Backend Engineer" from false-matching — Review Focus #1.)

- [x] **Step 1: Write the failing tests**

```python
# tests/unit/test_normalize.py
def test_normalize_text_strips_accents_case_and_punctuation():
    assert normalize_text("Sênior Dev, Remoto!") == "senior dev remoto"

def test_normalize_company_strips_legal_suffixes():
    assert normalize_company("Acme, Inc.") == "acme"
    assert normalize_company("Globex Corporation") == "globex"

def test_normalize_title_strips_remote_tokens():
    assert normalize_title("Backend Engineer (Remote)") == "backend engineer"

def test_dedup_key_format():
    assert dedup_key("Acme, Inc.", "Backend Engineer (Remote)") == "acme|backend engineer"

# tests/unit/test_dedup.py
def test_is_duplicate_matches_cross_source_variants():
    existing = [dedup_key("Acme, Inc.", "Backend Engineer")]
    assert is_duplicate(dedup_key("ACME", "Backend Engineer - Remote"), existing)
    assert is_duplicate(dedup_key("Acme LLC", "backend engineer"), existing)

def test_is_duplicate_keeps_distinct_roles_at_same_company():
    existing = [dedup_key("Acme", "Backend Engineer")]
    assert not is_duplicate(dedup_key("Acme", "Senior Backend Engineer"), existing)
    assert not is_duplicate(dedup_key("Acme", "Product Manager"), existing)
```

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/test_normalize.py tests/unit/test_dedup.py -v`
Expected: FAIL (`lookout.normalize` does not exist).

- [x] **Step 3: Implement `normalize.py` and `dedup.py`** per the pinned signatures and token rules.

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add normalization and fuzzy dedup" && git push origin HEAD
```

---

### Task 5: Collector framework + ingestion pipeline

**Files:**
- Create: `apps/api/lookout/collectors/__init__.py`, `apps/api/lookout/collectors/base.py`, `apps/api/lookout/ingest.py`, `tests/integration/test_ingest.py`
- Modify: `config/sources.yml` (full 13-source config if not completed in Task 1)
- Test: `tests/integration/test_ingest.py`

**Interfaces:**
- Consumes: `normalize.dedup_key`, `dedup.is_duplicate`, `openings.insert_opening/list_dedup_keys`, `Settings`.
- Produces:
  - `@dataclass(frozen=True) RawOpening` in `collectors/base.py`: `source: str`, `external_id: str | None`, `company: str`, `title: str`, `location: str | None`, `url: str`, `description: str`, `posted_at: datetime | None`, `raw: dict`.
  - `class Collector(Protocol)`: `name: str`; `fetch(self) -> list[RawOpening]`. `class CollectorError(Exception)`.
  - `@dataclass IngestStats`: `fetched: int = 0`, `inserted: int = 0`, `duplicates: int = 0`, `skipped: int = 0`, `errors: list[str] = field(default_factory=list)`.
  - `ingest(session: Session, raws: Iterable[RawOpening], *, company_threshold: float = 90.0, title_threshold: float = 90.0) -> IngestStats` — skips entries missing `company`/`title`/`url` (counted `skipped`); computes `dedup_key`; drops exact key repeats and fuzzy duplicates against DB keys **and keys inserted earlier in the same batch**; inserts the rest.
  - `collect_source(session: Session, collector: Collector, settings: Settings) -> IngestStats` — `fetch` + `ingest`; a `fetch` exception returns `IngestStats(errors=[str(exc)])` (never raises).
  - `collect_all(session: Session, collectors: Iterable[Collector], settings: Settings) -> dict[str, IngestStats]` — per-source isolation: one source's failure does not affect the others (Review Focus #3).
  - `config/sources.yml` shape (consumed by Task 15's `registry.build_collectors`):

```yaml
sources:
  remoteok:        {enabled: true,  interval_minutes: 360}
  remotive:        {enabled: true,  interval_minutes: 360}
  arbeitnow:       {enabled: true,  interval_minutes: 360}
  jobicy:          {enabled: true,  interval_minutes: 360}
  adzuna:          {enabled: false, interval_minutes: 720, countries: ["br", "us"], queries: ["python developer", "backend engineer"]}
  weworkremotely:  {enabled: true,  interval_minutes: 360}
  workingnomads:   {enabled: true,  interval_minutes: 360}
  himalayas:       {enabled: true,  interval_minutes: 360}
  hn_whoishiring:  {enabled: true,  interval_minutes: 720}
  greenhouse:      {enabled: true,  interval_minutes: 360, companies: {}}
  lever:           {enabled: true,  interval_minutes: 360, companies: {}}
  workable:        {enabled: false, interval_minutes: 360, companies: {}}
  linkedin_email:  {enabled: false, interval_minutes: 360}
```

- [x] **Step 1: Write the failing tests**

```python
# tests/integration/test_ingest.py
def test_ingest_inserts_new_and_counts_duplicates_within_batch(session):
    raws = [make_raw("Globex", "Backend Engineer"), make_raw("Globex, Inc.", "Backend Engineer (Remote)"),
            make_raw("Initech", "QA Engineer")]
    stats = ingest(session, raws)
    assert (stats.fetched, stats.inserted, stats.duplicates) == (3, 2, 1)

def test_ingest_rejects_duplicate_against_db(session):
    ingest(session, [make_raw("Globex", "Backend Engineer")])
    stats = ingest(session, [make_raw("Globex LLC", "Backend Engineer")])
    assert stats.inserted == 0 and stats.duplicates == 1

def test_ingest_skips_invalid_entries(session):
    stats = ingest(session, [make_raw(company="", url=""), make_raw("Globex", "Backend Engineer")])
    assert stats.skipped == 1 and stats.inserted == 1

def test_collect_all_isolates_failing_source(session):
    class Broken: name = "broken"
        def fetch(self): raise CollectorError("HTTP 500")
    class Ok: name = "ok"
        def fetch(self): return [make_raw("Globex", "Backend Engineer")]
    results = collect_all(session, [Broken(), Ok()], get_settings())
    assert results["broken"].errors and results["ok"].inserted == 1
```

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/integration/test_ingest.py -v`
Expected: FAIL (`lookout.collectors` does not exist).

- [x] **Step 3: Implement `collectors/base.py` and `ingest.py`** per the pinned signatures; finalize `config/sources.yml`.

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/integration -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add collector framework and ingestion pipeline" && git push origin HEAD
```

---

### Task 6: Tier 0 JSON API collectors (RemoteOK, Remotive, Arbeitnow, Jobicy)

**Files:**
- Create: `apps/api/lookout/collectors/remoteok.py`, `remotive.py`, `arbeitnow.py`, `jobicy.py`, `tests/fixtures/sources/{remoteok,remotive,arbeitnow,jobicy}.json`, `tests/unit/collectors/test_tier0_api.py`
- Test: `tests/unit/collectors/test_tier0_api.py`

**Interfaces:**
- Consumes: `collectors/base.py` (Task 5), `Settings`.
- Produces (per source `S` in `{remoteok, remotive, arbeitnow, jobicy}`): class `<S>Collector(Collector)` with `name = "<s>"`, `__init__(self, settings: Settings, client: httpx.Client | None = None)`, `fetch() -> list[RawOpening]`; and pure parser `parse_<s>(payload) -> list[RawOpening]`. Endpoint and field mapping (verified 2026-10-18):
  - **RemoteOK**: `GET https://remoteok.com/api` (send a browser-like `User-Agent`); JSON array — **first element is a metadata/legal object, skip it**; map `company`, `position`→title, `location`, `url`, `description` (HTML), `date`→posted_at, `id`→external_id.
  - **Remotive**: `GET https://remotive.com/api/remote-jobs`; `jobs[]`: `company_name`, `title`, `candidate_required_location`→location, `url`, `description`, `publication_date`, `id`.
  - **Arbeitnow**: `GET https://www.arbeitnow.com/api/job-board-api`; `data[]`: `company_name`, `title`, `location`, `url`, `description`, `created_at` (unix), `slug`→external_id.
  - **Jobicy**: `GET https://jobicy.com/api/v2/remote-jobs`; `jobs[]`: `companyName`, `jobTitle`→title, `jobGeo`→location, `url`, `jobDescription`→description, `pubDate`, `id`.
  - All parsers: malformed entries are skipped (never raise); `source` set to the collector `name`.

- [x] **Step 1: Write fixtures + failing tests**

Fixtures with fictional data (privacy rule), e.g. `remoteok.json`: metadata object + 2 jobs ("Globex"/"Senior Python Engineer", "Initech"/"Backend Developer") + 1 malformed entry missing `url`. One test per source:

```python
def test_parse_remoteok_maps_fields_and_skips_metadata():
    payload = json.loads(Path("tests/fixtures/sources/remoteok.json").read_text())
    jobs = parse_remoteok(payload)
    assert [j.company for j in jobs] == ["Globex", "Initech"]  # metadata + malformed skipped
    assert jobs[0].title == "Senior Python Engineer" and jobs[0].source == "remoteok"
    assert jobs[0].external_id and jobs[0].posted_at is not None
```
(Analogous tests for `parse_remotive`, `parse_arbeitnow`, `parse_jobicy` asserting company/title/location/url/description/posted_at/external_id from their fixtures.)

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/collectors/test_tier0_api.py -v`
Expected: FAIL (modules do not exist).

- [x] **Step 3: Implement the four collectors** (`fetch` via httpx with 30 s timeout; `parse_*` pure functions per the pinned mappings).

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit/collectors -v`
Expected: 4 PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add tier 0 json api collectors" && git push origin HEAD
```

---

### Task 7: Tier 0 RSS collectors (We Work Remotely, Working Nomads, Himalayas)

**Files:**
- Create: `apps/api/lookout/collectors/weworkremotely.py`, `workingnomads.py`, `himalayas.py`, `tests/fixtures/sources/{weworkremotely.xml,workingnomads.json,himalayas.xml}`, `tests/unit/collectors/test_tier0_rss.py`
- Test: `tests/unit/collectors/test_tier0_rss.py`

**Interfaces:**
- Consumes: `collectors/base.py`, `Settings`.
- Produces (same class + `parse_*` pattern as Task 6):
  - **We Work Remotely** (RSS, `GET https://weworkremotely.com/remote-jobs.rss`, verified 2026-10-18): item `title` is `"Company: Role"` — split on the **first** `": "`; `region`→location; `link`, `description`, `pubDate`, `guid`→external_id. Items without `": "` in the title are skipped.
  - **Working Nomads** (JSON, `GET https://www.workingnomads.com/api/exposed_jobs/`, verified 2026-10-18): array items: `company_name`, `title`, `location`, `url`, `description`, `pubdate`... (field names per fixture recorded from the live API; `id`→external_id).
  - **Himalayas** (RSS, `GET https://himalayas.app/jobs/rss`, verified 2026-10-18): namespaced fields `himalayasJobs:companyName`→company, `himalayasJobs:locationRestriction`→location; `title`, `link`, `content:encoded`→description (fall back to `description`), `pubDate`, `guid`→external_id. Use `feedparser` (handles the custom namespace).

- [x] **Step 1: Write fixtures + failing tests**

```python
def test_parse_weworkremotely_splits_company_and_title():
    jobs = parse_weworkremotely(Path("tests/fixtures/sources/weworkremotely.xml").read_text())
    assert jobs[0].company == "Globex" and jobs[0].title == "Senior Python Engineer"
    assert jobs[0].location == "Anywhere in the World"
```
(Analogous tests for `parse_workingnomads` and `parse_himalayas`, including: WWR item without `": "` skipped; Himalayas item using `content:encoded` for description.)

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/collectors/test_tier0_rss.py -v`
Expected: FAIL.

- [x] **Step 3: Implement the three collectors.**

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit/collectors -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add tier 0 rss collectors" && git push origin HEAD
```

---

### Task 8: Adzuna + HN "Who is Hiring" collectors

**Files:**
- Create: `apps/api/lookout/collectors/adzuna.py`, `hn_whoishiring.py`, `tests/fixtures/sources/{adzuna.json,hn_search.json,hn_item.json}`, `tests/unit/collectors/test_adzuna_hn.py`
- Test: `tests/unit/collectors/test_adzuna_hn.py`

**Interfaces:**
- Consumes: `collectors/base.py`, `Settings` (`adzuna_app_id/app_key`), sources config (`countries`, `queries`).
- Produces:
  - **Adzuna**: `AdzunaCollector(settings, countries: list[str], queries: list[str], client=None)`; `GET https://api.adzuna.com/v1/api/jobs/{country}/search/1` with params `app_id`, `app_key`, `results_per_page=50`, `what=<query>`; `parse_adzuna(payload: dict, country: str) -> list[RawOpening]`: `results[]` → `company.display_name`, `title`, `location.display_name`, `redirect_url`→url, `description`, `created`, `id`→external_id. `fetch` raises `CollectorError` if credentials are empty (recorded as source error, not a crash).
  - **HN "Who is Hiring"**: `HnWhoIsHiringCollector(settings, client=None)`; `fetch` finds the latest monthly thread via `GET https://hn.algolia.com/api/v1/search?tags=story,author_whoishiring&query=%22who%20is%20hiring%22` (API verified 2026-10-18; sort by `created_at_i` desc) then fetches `GET https://hn.algolia.com/api/v1/items/{story_id}` (full comment tree). `parse_hn_thread(item: dict, story_title: str) -> list[RawOpening]`: each top-level `children[]` comment is one posting; parse the first line split on `"|"` — `company = parts[0]`, `title = parts[1]`, `location = parts[2] if present`; **skip comments whose first line yields fewer than 2 parts**; `external_id = comment id`; `url = f"https://news.ycombinator.com/item?id={comment_id}"`; `description` = full comment HTML; `posted_at` = comment `created_at`; strip HTML tags for the first-line parse.

- [x] **Step 1: Write fixtures + failing tests**

```python
def test_parse_adzuna_maps_results():
    payload = json.loads(Path("tests/fixtures/sources/adzuna.json").read_text())
    jobs = parse_adzuna(payload, "br")
    assert jobs[0].company == "Globex" and jobs[0].url == "https://www.adzuna.com.br/details/123"
    assert jobs[0].external_id == "123"

def test_parse_hn_thread_extracts_pipe_delimited_postings():
    item = json.loads(Path("tests/fixtures/sources/hn_item.json").read_text())
    jobs = parse_hn_thread(item, "Ask HN: Who is hiring? (October 2026)")
    assert len(jobs) == 2  # malformed comment without pipes is skipped
    assert jobs[0].company == "Globex" and jobs[0].title == "Senior Python Engineer"
    assert jobs[0].location == "Remote" and jobs[0].url.endswith("item?id=4411")
```

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/collectors/test_adzuna_hn.py -v`
Expected: FAIL.

- [x] **Step 3: Implement both collectors.**

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit/collectors -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add adzuna and hn who is hiring collectors" && git push origin HEAD
```

---

### Task 9: Tier 1 ATS collectors (Greenhouse, Lever, Workable) + curated company list

**Files:**
- Create: `apps/api/lookout/collectors/greenhouse.py`, `lever.py`, `workable.py`, `tests/fixtures/sources/{greenhouse.json,lever.json,workable.json,workable_job.json}`, `tests/unit/collectors/test_tier1_ats.py`
- Test: `tests/unit/collectors/test_tier1_ats.py`

**Interfaces:**
- Consumes: `collectors/base.py`, `Settings`; `companies: dict[str, str]` (slug → display name) from `sources.yml`.
- Produces (same class + `parse_*` pattern; each collector iterates over the configured slugs, `source = f"<platform>"`, company = configured display name):
  - **Greenhouse**: `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` (shape verified 2026-10-18); `parse_greenhouse(payload: dict, company: str) -> list[RawOpening]`: `jobs[]` → `title`, `location.name`→location, `absolute_url`→url, `content`→description (HTML), `updated_at`→posted_at, `id`→external_id.
  - **Lever**: `GET https://api.lever.co/v0/postings/{slug}` (URL pattern pinned by PRD §5.1); `parse_lever(payload: list[dict], company: str) -> list[RawOpening]`: `text`→title, `categories.location`→location, `hostedUrl`→url, `descriptionPlain`→description, `createdAt` (ms epoch)→posted_at, `id`→external_id.
  - **Workable**: `POST https://apply.workable.com/api/v3/accounts/{slug}/jobs` with JSON body `{"query": "", "location": [], "department": [], "worktype": [], "remote": []}` → `results[]`: `title`, `shortcode`→external_id, `country`/`city`→location, url = `f"https://apply.workable.com/{slug}/j/{shortcode}/"`; then per job `GET https://apply.workable.com/api/v3/accounts/{slug}/jobs/{shortcode}` for the description. `parse_workable(payload: dict, slug: str, company: str) -> list[RawOpening]` (list only; descriptions filled by `fetch` from detail responses). **Escape hatch:** if this endpoint shape proves wrong at acceptance, disable Workable in `sources.yml` and drop it from Phase 1 (collection failure → source dropped, Q10).

- [x] **Step 1: Write fixtures + failing tests**

```python
def test_parse_greenhouse_uses_configured_company_name():
    payload = json.loads(Path("tests/fixtures/sources/greenhouse.json").read_text())
    jobs = parse_greenhouse(payload, "Globex")
    assert jobs[0].company == "Globex" and jobs[0].title == "Senior Python Engineer"
    assert jobs[0].url.startswith("https://job-boards.greenhouse.io/") and "<p>" in jobs[0].description

def test_parse_lever_maps_fields():
    jobs = parse_lever(json.loads(Path("tests/fixtures/sources/lever.json").read_text()), "Initech")
    assert jobs[0].title == "Backend Developer" and jobs[0].location == "São Paulo, Brazil"

def test_parse_workable_builds_apply_urls():
    jobs = parse_workable(json.loads(Path("tests/fixtures/sources/workable.json").read_text()), "hooli", "Hooli")
    assert jobs[0].url == "https://apply.workable.com/hooli/j/9F8E7D6C5A/" and jobs[0].external_id == "9F8E7D6C5A"
```

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/collectors/test_tier1_ats.py -v`
Expected: FAIL.

- [x] **Step 3: Implement the three collectors.**

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit/collectors -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add tier 1 ats collectors" && git push origin HEAD
```

---

### Task 10: LinkedIn email alerts collector (Gmail API)

**Files:**
- Create: `apps/api/lookout/collectors/linkedin_email.py`, `tests/fixtures/sources/linkedin_alert.html`, `tests/unit/collectors/test_linkedin_email.py`
- Test: `tests/unit/collectors/test_linkedin_email.py`

**Interfaces:**
- Consumes: `collectors/base.py`, `Settings` (`gmail_*`).
- Produces:
  - `parse_linkedin_alert(subject: str, html_body: str) -> list[RawOpening]` — extracts job cards from a LinkedIn job-alert email; canonicalizes links with the regex `https://www\.linkedin\.com/(?:comm/)?jobs/view/(\d+)` → `external_id` = the numeric id, `url` = `f"https://www.linkedin.com/jobs/view/{id}"`; company/title from the card markup; `source = "linkedin_email"`; `posted_at = None`; `raw = {"subject": subject}`. Non-job emails yield `[]`.
  - `class LinkedInEmailCollector(Collector)`: `fetch()` builds the Gmail service (`googleapiclient.discovery.build("gmail", "v1", credentials=creds)`), lists `users().messages().list(q=f"label:{settings.gmail_label} from:jobs-noreply@linkedin.com newer_than:7d")`, fetches each with `format="full"`, extracts subject + `text/html` body part, feeds `parse_linkedin_alert`.
  - `load_gmail_credentials(settings: Settings) -> Credentials` — loads `settings.gmail_token_file`, refreshes if expired; raises `CollectorError` with instructions if missing.
  - `run_gmail_auth(settings: Settings) -> None` — `InstalledAppFlow.from_client_secrets_file(settings.gmail_credentials_file, scopes=["https://www.googleapis.com/auth/gmail.readonly"]).run_local_server(port=0)`, writes token JSON to `settings.gmail_token_file` (under gitignored `data/`). Exposed as `python -m lookout.cli gmail-auth` in Task 15.

- [x] **Step 1: Write fixture + failing tests**

Fixture `linkedin_alert.html`: fictional alert with 2 job cards (Globex/"Senior Python Engineer" id 4311001, Initech/"Backend Developer" id 4311002) containing `/comm/jobs/view/` links with tracking params, plus one promotional block with no job link.

```python
def test_parse_linkedin_alert_extracts_canonical_jobs():
    html = Path("tests/fixtures/sources/linkedin_alert.html").read_text()
    jobs = parse_linkedin_alert("2 new jobs for \"python remote\"", html)
    assert [(j.company, j.title) for j in jobs] == [("Globex", "Senior Python Engineer"), ("Initech", "Backend Developer")]
    assert jobs[0].external_id == "4311001"
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/4311001"  # tracking stripped

def test_parse_linkedin_alert_ignores_non_job_emails():
    assert parse_linkedin_alert("Your weekly summary", "<html><body>No jobs</body></html>") == []
```

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/collectors/test_linkedin_email.py -v`
Expected: FAIL.

- [x] **Step 3: Implement `linkedin_email.py`** (parser pure and tested; Gmail transport thin and untested — verified manually at acceptance).

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit/collectors -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add linkedin email alerts collector" && git push origin HEAD
```

---

### Task 11: Knowledge base loader + starter template

**Files:**
- Create: `apps/api/lookout/kb.py`, `templates/kb/{identity.md,summary.md,skills.md,languages.md,education.md}`, `templates/kb/experiences/exp-acme.md`, `templates/kb/projects/proj-payments.md`, `tests/fixtures/kb/**` (fictional mirror), `tests/unit/test_kb.py`
- Test: `tests/unit/test_kb.py`

**Interfaces:**
- Consumes: nothing. Consumed by: Tasks 12–14.
- Produces:
  - `@dataclass(frozen=True) PiiProfile`: `full_name: str`, `cpf: str`, `phone: str`, `address: str`, `email: str` (re-exported from `redaction.py` — define it in Task 12; until then `kb.py` holds it and Task 12 moves it: **final home is `redaction.py`, `kb.py` imports it**).
  - `@dataclass Experience`: `id: str`, `company: str`, `role: str`, `start: str`, `end: str | None`, `summary: str`, `highlights: list[str]`, `tech: list[str]`. `@dataclass Project`: `id: str`, `name: str`, `summary: str`, `highlights: list[str]`, `tech: list[str]`.
  - `@dataclass KnowledgeBase`: `identity: PiiProfile`, `summary: str`, `experiences: list[Experience]`, `projects: list[Project]`, `skills: list[str]`, `languages: list[str]`, `education: list[str]`.
  - `load_knowledge_base(path: Path) -> KnowledgeBase` — `identity.md` frontmatter: `full_name, cpf, phone, address, email`; `experiences/*.md` and `projects/*.md` frontmatter carries the structured fields, body is the long description; `skills.md`/`languages.md`/`education.md` frontmatter `items: [...]`. Parsed with `python-frontmatter`. Raises `KnowledgeBaseError` listing missing required files.
  - `kb_to_prompt_text(kb: KnowledgeBase) -> str` — deterministic serialization of the KB for the LLM prompt: every experience/project line tagged with its `id` (e.g. `[exp-acme]`), so the LLM output can cite ids for validation.
  - `templates/kb/` committed with a **fictional** persona (privacy rule); user copies it to `data/kb/`.

- [x] **Step 1: Write fixture KB + failing test**

Fixture `tests/fixtures/kb/`: `identity.md` (Maria Silva, CPF `123.456.789-09`, `+55 11 98765-4321`, `Rua das Flores, 123 - São Paulo/SP`, `maria.silva@example.com`), `experiences/exp-acme.md`, `projects/proj-lookout.md`, skills `[Python, FastAPI, PostgreSQL]`.

```python
def test_load_knowledge_base_reads_all_sections():
    kb = load_knowledge_base(Path("tests/fixtures/kb"))
    assert kb.identity.full_name == "Maria Silva"
    assert kb.experiences[0].id == "exp-acme" and kb.experiences[0].tech == ["Python", "FastAPI"]
    assert kb.skills == ["Python", "FastAPI", "PostgreSQL"]

def test_load_knowledge_base_errors_on_missing_identity(tmp_path):
    with pytest.raises(KnowledgeBaseError):
        load_knowledge_base(tmp_path)

def test_kb_to_prompt_text_tags_facts_with_ids():
    text = kb_to_prompt_text(load_knowledge_base(Path("tests/fixtures/kb")))
    assert "[exp-acme]" in text and "[proj-lookout]" in text
```

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/test_kb.py -v`
Expected: FAIL.

- [x] **Step 3: Implement `kb.py` + the `templates/kb/` starter.**

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit/test_kb.py -v`
Expected: 3 PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add knowledge base loader and starter template" && git push origin HEAD
```

---

### Task 12: PII redaction layer

**Files:**
- Create: `apps/api/lookout/redaction.py`, `tests/unit/test_redaction.py`
- Modify: `apps/api/lookout/kb.py` (import `PiiProfile` from `redaction.py`)
- Test: `tests/unit/test_redaction.py`

**Interfaces:**
- Consumes: nothing (imports no other lookout module; `kb.py` imports `PiiProfile` from here).
- Produces:
  - `@dataclass(frozen=True) PiiProfile`: `full_name`, `cpf`, `phone`, `address`, `email` (all `str`).
  - `redact(text: str, pii: PiiProfile) -> str` — replaces, case-insensitively, every non-empty profile literal with its placeholder (`[CANDIDATE_NAME]`, `[CPF]`, `[PHONE]`, `[ADDRESS]`, `[EMAIL]`); then applies regexes anywhere in the text: CPF `\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b`, BR phone `(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}`. Over-redaction of digit runs is acceptable (privacy-favored).
  - `contains_pii(text: str, pii: PiiProfile) -> bool` — True if any profile literal or CPF/phone regex matches; used as a post-redaction assertion (Review Focus #2).
  - PRD pins name/CPF/phone/address (Q14, F6); email is redacted as an extra safeguard.

- [x] **Step 1: Write the failing tests**

```python
PII = PiiProfile(full_name="Maria Silva", cpf="123.456.789-09",
                 phone="+55 11 98765-4321", address="Rua das Flores, 123 - São Paulo/SP",
                 email="maria.silva@example.com")

def test_redact_replaces_identity_fields():
    out = redact("Maria Silva — maria.silva@example.com — Rua das Flores, 123 - São Paulo/SP", PII)
    assert "Maria Silva" not in out and "maria.silva@example.com" not in out
    assert "[CANDIDATE_NAME]" in out and "[EMAIL]" in out and "[ADDRESS]" in out

def test_redact_catches_pii_inside_free_text():
    out = redact("Led migration; reach me at 11 98765-4321 or 987.654.321-00", PII)
    assert "98765-4321" not in out and "987.654.321-00" not in out

def test_redact_keeps_company_names():
    assert "Globex Corporation" in redact("Backend Engineer at Globex Corporation", PII)

def test_contains_pii():
    assert contains_pii("call 123.456.789-09", PII)
    assert not contains_pii("[CPF] available on request", PII)
```

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/test_redaction.py -v`
Expected: FAIL.

- [x] **Step 3: Implement `redaction.py`; move `PiiProfile` there and update `kb.py` to import it.**

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit -v`
Expected: all PASS (including Task 11 tests unchanged).

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add pii redaction layer" && git push origin HEAD
```

---

### Task 13: OpenRouter client + tailor prompt + KB-only validation

**Files:**
- Create: `apps/api/lookout/llm.py`, `apps/api/lookout/tailor/__init__.py`, `apps/api/lookout/tailor/schema.py`, `apps/api/lookout/tailor/prompts.py`, `apps/api/lookout/tailor/validation.py`, `tests/unit/test_llm.py`, `tests/unit/test_tailor_prompts.py`, `tests/unit/test_tailor_validation.py`
- Test: the three test files above

**Interfaces:**
- Consumes: `Settings` (`openrouter_*`), `KnowledgeBase`, `kb_to_prompt_text`, `Opening` (type only).
- Produces:
  - `class LLMError(Exception)`; `class OpenRouterClient`: `__init__(self, *, api_key: str, model: str, base_url: str = "https://openrouter.ai/api/v1", client: httpx.Client | None = None)`; `complete_json(self, *, system: str, user: str) -> dict` — `POST {base_url}/chat/completions` with `Authorization: Bearer <key>`, body `{"model": model, "messages": [...], "response_format": {"type": "json_object"}}`; returns `json.loads(choices[0].message.content)`; raises `LLMError` on HTTP errors, timeouts and invalid JSON.
  - `class TailoredResume(BaseModel)` (`tailor/schema.py`): `language: Literal["pt-br", "en"]`, `summary: str`, `experiences: list[TailoredExperience]`, `projects: list[TailoredProject]`, `skills: list[str]`; `TailoredExperience/TailoredProject` = `{kb_id: str, highlights: list[str]}`.
  - `build_tailor_prompt(*, opening: Opening, kb_text: str, language: str) -> tuple[str, str]` — system prompt pins the guardrail verbatim: *"Use ONLY facts present in the knowledge base below. Never invent employers, roles, dates, projects or skills. Every experience and project in your output must carry the exact kb_id from the knowledge base. Output JSON only."* + language-follows-posting instruction; user prompt = opening (company/title/description) + `kb_text`.
  - `validate_resume(resume: TailoredResume, kb: KnowledgeBase) -> list[str]` — violation per `kb_id` not present in the KB and per skill not in `kb.skills` (case-insensitive); empty list = valid (R1/F2 guardrail).

- [x] **Step 1: Write the failing tests**

```python
# tests/unit/test_llm.py
def test_complete_json_posts_to_openrouter_and_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})
    llm = OpenRouterClient(api_key="test-key", model="test-model",
                           client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert llm.complete_json(system="s", user="u") == {"ok": True}

def test_complete_json_raises_on_http_error():
    llm = OpenRouterClient(api_key="k", model="m",
                           client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json={}))))
    with pytest.raises(LLMError):
        llm.complete_json(system="s", user="u")

# tests/unit/test_tailor_validation.py
def test_validation_flags_fabricated_facts(kb):
    resume = TailoredResume(language="en", summary="...", skills=["Python", "Kubernetes"],
                            experiences=[TailoredExperience(kb_id="exp-ghost", highlights=["Invented"])],
                            projects=[])
    violations = validate_resume(resume, kb)
    assert any("exp-ghost" in v for v in violations) and any("Kubernetes" in v for v in violations)

def test_validation_accepts_kb_only_resume(kb):
    assert validate_resume(valid_fixture_resume(), kb) == []

# tests/unit/test_tailor_prompts.py
def test_prompt_contains_guardrail_redacted_kb_and_posting(kb, opening):
    system, user = build_tailor_prompt(opening=opening, kb_text=kb_to_prompt_text(kb), language="en")
    assert "Never invent" in system
    assert "[exp-acme]" in user and opening.title in user and opening.company in user
```

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/test_llm.py tests/unit/test_tailor_prompts.py tests/unit/test_tailor_validation.py -v`
Expected: FAIL.

- [x] **Step 3: Implement the modules** per the pinned signatures (fixtures: reuse `tests/fixtures/kb`; add `tests/fixtures/tailor/` resume JSONs).

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add openrouter client and tailor prompt validation" && git push origin HEAD
```

---

### Task 14: Resume rendering, PDF and the tailor pipeline

**Files:**
- Create: `apps/api/lookout/tailor/render.py`, `apps/api/lookout/tailor/pdf.py`, `apps/api/lookout/tailor/pipeline.py`, `templates/resume/base.html`, `templates/resume/resume.css`, `tests/fixtures/tailor/llm_response_en.json`, `tests/fixtures/tailor/llm_response_ptbr.json`, `tests/unit/test_render.py`, `tests/integration/test_tailor_pipeline.py`
- Test: `tests/unit/test_render.py`, `tests/integration/test_tailor_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 11–13; `openings.get_opening`; `Opening`.
- Produces:
  - `detect_language(text: str) -> Literal["pt-br", "en"]` — small stopword heuristic (pt-br: `de, para, com, você, experiência, vaga, trabalho`; en: `the, and, for, with, you, experience, job`); default `"en"` on tie.
  - `render_resume_html(resume: TailoredResume, kb: KnowledgeBase) -> str` — Jinja2 `templates/resume/base.html` + `resume.css`; single column; standard headings localized (`en`: Summary/Experience/Projects/Skills/Education; `pt-br`: Resumo/Experiência/Projetos/Competências/Formação); contact header rendered **from `kb.identity` (not from LLM output)**; experience/project content resolved from `kb_id` + tailored `highlights`.
  - `html_to_pdf(html: str, out_path: Path) -> Path` — WeasyPrint; creates parent dirs.
  - `class TailorError(Exception)`; `tailor_resume(session: Session, *, opening_id: uuid.UUID, kb_path: Path, out_dir: Path, llm: OpenRouterClient) -> Path` — orchestrates: load opening (raise `TailorError` if missing) → load KB → `kb_to_prompt_text` → `redact` → **assert `not contains_pii(...)` else raise `TailorError`** → `detect_language(opening.description)` → `build_tailor_prompt` → `llm.complete_json` → `TailoredResume.model_validate` → `validate_resume` (violations → raise `TailorError` listing them) → `render_resume_html` → `html_to_pdf` to `out_dir / f"{opening_id}.pdf"` → return path.

- [x] **Step 1: Write fixtures + failing tests**

```python
# tests/unit/test_render.py
def test_render_localizes_headings_and_uses_kb_identity(kb):
    resume = TailoredResume.model_validate(json.loads(Path("tests/fixtures/tailor/llm_response_ptbr.json").read_text()))
    html = render_resume_html(resume, kb)
    assert "Experiência" in html and "Maria Silva" in html  # identity from KB, not from LLM output

# tests/integration/test_tailor_pipeline.py
KB_FIXTURE = Path("tests/fixtures/kb")
SELF_PII = load_knowledge_base(KB_FIXTURE).identity

class FakeLLM:
    def __init__(self, response: dict): self._response = response
    def complete_json(self, *, system: str, user: str) -> dict:
        assert not contains_pii(system + user, SELF_PII)  # PII never reaches the LLM payload
        return self._response

def test_tailor_resume_produces_real_text_pdf(tmp_path, session, opening_fixture):
    pdf_path = tailor_resume(session, opening_id=opening_fixture.id, kb_path=Path("tests/fixtures/kb"),
                             out_dir=tmp_path, llm=FakeLLM(load_json("llm_response_en.json")))
    text = pypdf.PdfReader(str(pdf_path)).pages[0].extract_text()
    assert "Experience" in text and "Maria Silva" in text

def test_tailor_resume_rejects_fabricated_llm_output(tmp_path, session, opening_fixture):
    with pytest.raises(TailorError):
        tailor_resume(session, opening_id=opening_fixture.id, kb_path=Path("tests/fixtures/kb"),
                      out_dir=tmp_path, llm=FakeLLM(load_json("llm_response_invalid.json")))
    assert list(tmp_path.iterdir()) == []  # no PDF written

def test_detect_language():
    assert detect_language("Vaga para desenvolvedor Python com experiência") == "pt-br"
    assert detect_language("We are looking for a Python developer with experience") == "en"
```
(`opening_fixture` inserts a fictional opening; `llm_response_invalid.json` cites `exp-ghost` and skill `Kubernetes`.)

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/test_render.py tests/integration/test_tailor_pipeline.py -v`
Expected: FAIL.

- [x] **Step 3: Implement `render.py`, `pdf.py`, `pipeline.py` and the resume templates.**

- [x] **Step 4: Run to verify it passes**

Run: `docker compose exec api pytest tests/unit tests/integration -v`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add resume tailor pipeline with pdf output" && git push origin HEAD
```

---

### Task 15: API endpoints, CLI, worker scheduling, README

**Files:**
- Create: `apps/api/lookout/collectors/registry.py`, `tests/unit/test_registry.py`, `tests/unit/test_api.py`, `tests/unit/test_worker.py`
- Modify: `apps/api/lookout/api.py` (endpoints), `apps/api/lookout/worker.py` (full scheduler), `apps/api/lookout/cli.py` (new), `README.md` (add "Running (Phase 1 MVP)" section: prerequisites, `cp .env.example .env`, copy `templates/kb` → `data/kb`, `docker compose up -d --build`, CLI/API trigger examples)
- Test: `tests/unit/test_api.py`, `tests/unit/test_worker.py`, `tests/unit/test_registry.py`

**Interfaces:**
- Consumes: all previous tasks.
- Produces:
  - `registry.py`: `load_sources_config(path: Path) -> dict[str, dict]` (PyYAML); `get_collector(name: str, settings: Settings, config: dict) -> Collector`; `build_collectors(settings: Settings, config: dict) -> list[Collector]` (enabled sources only); `COLLECTOR_NAMES: list[str]` (the 13 sources).
  - `api.py` additions: `create_app(settings: Settings | None = None)` stores `engine` on `app.state`; `get_session(request: Request) -> Iterator[Session]` (FastAPI dependency); `GET /openings?limit&offset -> list[Opening]`; `POST /collect` (optional body `{"source": name}`) → `202 {"enqueued": n}` (one `collect` job per enabled source, or one for the named source; 404 on unknown source); `POST /openings/{opening_id}/tailor` → `202 {"job_id": str}` (404 if the opening does not exist).
  - `worker.py`: `process_next_job(session, settings) -> bool`; `enqueue_collect_job(settings, source: str) -> None`; `main()` — `BackgroundScheduler` with: queue poll every `settings.worker_poll_seconds` (`max_instances=1`), `reap_stale` every 10 min, and one interval job per enabled source (`minutes=cfg["interval_minutes"]`) calling `enqueue_collect_job`. `JOB_HANDLERS: dict[str, Callable[[Session, Settings, dict], None]]` = `{"collect": handle_collect, "tailor": handle_tailor}`; `handle_collect` runs `collect_all`/`collect_source`; `handle_tailor` runs `tailor_resume` with `settings.kb_path`, `settings.artifacts_dir` and an `OpenRouterClient` from settings. Handler exceptions → `queue.fail`; success → `queue.complete`.
  - `cli.py` (`python -m lookout.cli`, argparse): `collect [--source NAME] [--enqueue]` (default: runs synchronously and prints `IngestStats` per source), `tailor OPENING_ID` (synchronous, prints PDF path), `gmail-auth`, `list-openings [--limit N]`.

- [x] **Step 1: Write the failing tests**

```python
# tests/unit/test_api.py
def test_health(client): assert client.get("/health").json() == {"status": "ok"}

def test_list_openings(client, session):
    insert_opening(session, make_raw("Globex", "Backend Engineer"))
    assert [o["company"] for o in client.get("/openings").json()] == ["Globex"]

def test_post_collect_enqueues_one_job_per_enabled_source(client, session):
    r = client.post("/collect", json={})
    assert r.status_code == 202 and r.json()["enqueued"] >= 1

def test_post_tailor_enqueues_job(client, session):
    opening = insert_opening(session, make_raw("Globex", "Backend Engineer"))
    r = client.post(f"/openings/{opening.id}/tailor")
    assert r.status_code == 202 and r.json()["job_id"]

def test_post_tailor_404_on_unknown_opening(client):
    assert client.post(f"/openings/{uuid4()}/tailor").status_code == 404

# tests/unit/test_worker.py
def test_process_next_job_dispatches_and_completes(session, settings, monkeypatch):
    job = enqueue(session, "collect", {"source": "fake"})
    monkeypatch.setitem(JOB_HANDLERS, "collect", lambda s, st, p: None)
    assert process_next_job(session, settings) is True
    session.refresh(job)
    assert job.status == "done"

def test_process_next_job_marks_failure(session, settings, monkeypatch):
    job = enqueue(session, "collect", {"source": "fake"}, max_attempts=1)
    def boom(s, st, p): raise RuntimeError("collector exploded")
    monkeypatch.setitem(JOB_HANDLERS, "collect", boom)
    process_next_job(session, settings)
    session.refresh(job)
    assert job.status == "failed" and "collector exploded" in job.last_error
```
(The API tests build the app with test settings and override `get_session` via `app.dependency_overrides`; add fixtures to `tests/conftest.py`. A `fake` collector is registered in the test's config dict — registry accepts injected collectors.)

- [x] **Step 2: Run to verify it fails**

Run: `docker compose exec api pytest tests/unit/test_api.py tests/unit/test_worker.py tests/unit/test_registry.py -v`
Expected: FAIL.

- [x] **Step 3: Implement `registry.py`, the API endpoints, the full worker and the CLI; update README.**

- [x] **Step 4: Run to verify it passes + full suite green**

Run: `docker compose up -d --build && docker compose exec api pytest -v && docker compose exec api ruff check .`
Expected: all PASS, ruff clean.

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add api endpoints, cli and worker scheduling" && git push origin HEAD
```

---

### Task 16: Phase 1 acceptance walkthrough

**Files:**
- Create: `docs/runbooks/phase-1-acceptance.md` (record the executed commands and observed outputs)

This task runs the MVP end-to-end against real services. It requires an `OPENROUTER_API_KEY`; Adzuna and LinkedIn steps are optional (need credentials/OAuth bootstrap).

- [x] **Step 1: Prepare local data**

`cp .env.example .env` and fill `OPENROUTER_API_KEY`; `cp -r templates/kb data/kb` (fictional persona or the user's real KB — never committed).

- [x] **Step 2: Boot the stack**

Run: `docker compose up -d --build && docker compose ps`
Expected: `postgres` and `api` healthy, `worker` running; `docker compose exec api alembic current` shows `0002` (or later).

- [x] **Step 3: Collect real openings**

Run: `docker compose exec api python -m lookout.cli collect --source remoteok`
Expected: output stats with `inserted > 0`, no errors. Repeat the same command: `duplicates > 0` and `inserted == 0` (F4 dedup works on re-run).

- [x] **Step 4: Collect everything enabled**

Run: `docker compose exec api python -m lookout.cli collect`
Expected: per-source stats for all enabled sources; sources without credentials/config (adzuna, greenhouse/lever with empty company lists, linkedin_email, workable) report an error or zero results **without aborting the run**.

- [ ] **Step 5: Generate a tailored resume with a real LLM call**

Run: `docker compose exec api python -m lookout.cli list-openings` then `docker compose exec api python -m lookout.cli tailor <OPENING_ID>`
Expected: a PDF at `data/artifacts/<OPENING_ID>.pdf`; open it and confirm: correct language (follows the posting), real selectable text, content consistent with `data/kb` (no invented facts).

- [x] **Step 6: Verify the queue path (API → worker)**

Run: `curl -X POST localhost:8000/collect -H 'Content-Type: application/json' -d '{"source": "remoteok"}'` and watch `docker compose logs -f worker`
Expected: the worker claims the `collect` job and completes it (`status=done` visible in logs / DB).

- [x] **Step 7: (Optional) Gmail OAuth bootstrap + LinkedIn alerts** — skipped because Gmail credentials were unavailable.

Run: `docker compose exec api python -m lookout.cli gmail-auth` (needs `data/gmail_credentials.json` from Google Cloud Console with the Gmail API enabled) then enable `linkedin_email` in `config/sources.yml` and `collect --source linkedin_email`
Expected: LinkedIn alert emails under the configured label become openings with canonical `linkedin.com/jobs/view/<id>` URLs.

- [x] **Step 8: Full verification + record results**

Run: `docker compose exec api pytest -v && docker compose exec api ruff check . && docker compose exec api ruff format --check .`
Expected: all green. Write the commands + observed outputs into `docs/runbooks/phase-1-acceptance.md`.

- [ ] **Step 9: Commit and push** (major point per `.opencode/rules/git-workflow.md`)

```bash
git add -A && git commit -m "docs: record phase 1 acceptance results" && git push origin HEAD
```

---

## Self-Review Notes

- **Spec coverage:** PRD §7 Phase 1 = Collector Tier 0 (Tasks 6–8: all nine sources incl. Adzuna per §5.1), Tier 1 (Task 9), LinkedIn email alerts (Task 10), State DB (Task 2), Resume Tailor prototype manually triggered (Tasks 11–14, triggered via CLI/API in Task 15). Enabling infra: queue/scheduler (S2, Task 3 + 15), dedup at ingestion (F4, Tasks 4–5), PII redaction before LLM calls (Q14, Tasks 12–14), repo layout/compose (S9/F1, Task 1). No Phase 2/3 scope included.
- **Out of scope (deliberately):** Matcher/scoring, lanes, Applier, Screener, facts table, MinIO, Infisical, frontend, Tier 2 sources, Playwright (Phase 2 — dependency intentionally not installed yet).
- **Type consistency:** `RawOpening`, `IngestStats`, `PiiProfile`, `KnowledgeBase`, `TailoredResume`, `Opening`, `Job` and all cross-task function signatures are defined once (in the owning task's Interfaces block) and referenced by name elsewhere.
