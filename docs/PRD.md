# Lookout — Product Requirements Document

> Status: Agent requirements **FROZEN** (Q1–Q16, F1–F10, C1). Stack **FROZEN** (§11, round S).
> Next: Phase 1 implementation plan. Language of record: English; conversation in pt-br.

## 1. Problem Statement

Automating job hunting end-to-end: collecting openings from configured sources,
judging fit against the user's profile, tailoring a resume per opening, and
executing the application where automation is viable — with a curated
manual-assist lane everywhere else.

## 2. Goals

- Collect ~500 openings/month from configured sources (Q16).
- Execute ~100 applications/month on automatable platforms (Q16).
- ≥95% of auto-submitted applications at a quality the user would approve
  without review (Q16).
- Direct PII (name, CPF, phone, address) NEVER sent to external LLMs (Q14, F6).
- The agent never messages recruiters/companies; it only submits applications (Q1).

## 3. Non-Goals

- Post-application follow-up, interview tracking, recruiter outreach (Q15, Q1).
- Platforms with internal "profilation" instead of resume upload (e.g. **Gupy**)
  — entirely out of scope (F9).
- LinkedIn direct scraping/automation — LinkedIn is email-alerts only (Q4).
- Re-application to previously applied openings — never (F4).

## 4. The Three Lanes (autonomy model — Q1, Q2, Q7)

Every collected opening is routed to exactly one lane:

| Lane | Criteria | What happens |
|------|----------|--------------|
| **Auto-apply** | High match score + automatable platform | Resume tailored, application submitted without human review. Record + artifacts stored (Q1). |
| **Review queue** | Borderline score, automatable platform | Resume tailored, waits for user OK. **TTL: 1 week**, then expires (F8). User can also close manually; every opening carries its source link (F8). |
| **Manual-assist** | Non-automatable platform, or declined in review | Opening + tailored resume in the UI; user submits manually on the source site (Q2). |
| **Rejected** | Low score | Logged, discarded. |

**Dry-run mode** exists end-to-end (everything except final submit) — used by
the manual-assist lane and for testing connectors (Q3).

**Automatable platform (de facto criteria — F9):** apply without login, OR login
stable without recurring CAPTCHA; standard web form or email apply.
In: **Greenhouse, Lever, email**. Out: LinkedIn, Gupy and similar (F9).

## 5. Functional Modules

### 5.1 Collector
- Queue-based pipeline, ~100% uptime, Docker on the user's local machine (Q5, F1).
- MVP source coverage (Q4):
  - **Tier 0** — official APIs/RSS: RemoteOK, Remotive, Arbeitnow, Jobicy,
    Adzuna, We Work Remotely, Working Nomads, Himalayas, HN "Who is Hiring".
  - **Tier 1** — ATS public JSON: curated company list on Greenhouse
    (`boards.greenhouse.io/{co}`) and Lever (`api.lever.co/v0/postings/{co}`); Workable.
  - **Tier 2** — BR/LatAm: Programathor, Trampos.co, Coodesh, GeekHunter, Revelo,
    Indeed BR, Vagas.com, Catho, InfoJobs, Landing.jobs.
  - **Tier 3** — LinkedIn **via email alerts parsing only** (Q4).
- **Dedup at ingestion (F4):** key = normalized (company + title) + description
  similarity (cheap embedding or fuzzy hash). Duplicates never enter the DB;
  re-posts are never re-applied.

### 5.2 Matcher (approved funnel — Q6, F5)
1. **Deterministic pre-filter** (zero cost): include/exclude keywords, posting
   language, location/regime (worldwide-remote vs geo-locked), seniority regex,
   salary range when present.
2. **Cheap LLM scoring** (Haiku/Flash-class via OpenRouter): user match profile +
   fixed rubric → structured JSON `{score 0–100, reasons[], red_flags[]}`.
3. **Score bands** (configurable in UI): `≥X` auto-apply (if automatable),
   `Y–X` review queue, `<Y` reject.
- The **match profile** (ideal job, dealbreakers) is user-written from a template
  provided by the project (F5).

### 5.3 Profile Store (Q13)
- **Knowledge base**: Markdown + frontmatter (Obsidian-compatible): experiences,
  projects (detailed: what was used, what was done), skills, languages, education.
  Read by the LLM. Content is user homework.
- **State DB**: **PostgreSQL from day one** (decision S7: Infisical requires
  Postgres, so it becomes the standard DB for the whole app): openings,
  applications, lanes, dedup keys, audit log.
- **Artifacts**: submitted resume PDFs, answers, per-opening short records —
  stored in **MinIO (self-hosted, S3-compatible, Docker)** (F1).

### 5.4 Resume Tailor (Q11, Q12)
- Selects/rewrites ONLY facts present in the knowledge base; never invents (Q12).
- Permanent sections + adaptable experience/tools sections (Q12).
- Output: PDF, language follows the posting (PT-BR/EN), strongly ATS-friendly
  (single-column, standard headings, real text — detailed ATS research later).
- **Error taxonomy (F2 — pending confirmation C1):**
  - UNACCEPTABLE: content fabrication — e.g. swapping one project's description
    for another, invented experience.
  - Acceptable: surface-level inaccuracies — company-name abbreviation variants,
    minor numeric rounding.
- Generation tech: deferred to stack phase (Jinja2 + HTML→PDF or Typst) (F10).

### 5.5 Screener (Q9, F3)
Resolution order for screening questions:
1. **Pre-approved facts table** (work authorization, salary min/max, start date,
   relocation, etc.) — deterministic, user-maintained.
2. **LLM inference** — ONLY for an enumerated list of inferable question classes
   (list to be defined alongside the facts-table spec); never free-generation
   for disqualifying factual questions.
3. Otherwise → **impediment queue** (blocks the application for user input) or
   manual-assist lane (Q9).

### 5.6 Applier (Q8, Q10)
- Deterministic fill for data already in the DB; LLM for subjective questions (Q8).
- Login/CAPTCHA/2FA failure → downgrade to manual-assist; collection failure →
  source dropped (Q10).
- Per-platform connectors; Greenhouse/Lever/email first (F9).

### 5.7 Credentials & Sessions (F7)
- **Google SSO preferred** wherever a platform offers it; otherwise credentials
  stored in a **secrets vault service** (Docker Compose).
- Frontend section for credential management, API-key-like UX (F7).
- Daily per-connector health check + UI alert on session expiry (F7).
- ⚠ Known risk (R6): Google actively blocks automated logins — SSO works via
  **persistent browser session** (manual first login, agent reuses the profile),
  not via automated OAuth flow.

## 6. LLM Usage & Privacy (Q14, F6)

- External LLM (cheap + fast, OpenRouter-class gateway; no local LLM — F1)
  receives: job posting + experience/project descriptions (company names OK — F6).
- **PII redaction layer** before every LLM call: name, CPF, phone, address never
  leave the machine (Q14).
- All infra runs locally via Docker Compose; only LLM inference is external (F1).

## 7. Phasing (F5)

- **Phase 1 — MVP:** Collector (Tier 0 + Tier 1 + LinkedIn email alerts) + State
  DB + Resume Tailor prototype (knowledge base → tailored PDF), manually triggered.
  No frontend.
- **Phase 2 — Automation loop:** Matcher funnel, three lanes, Applier
  (Greenhouse/Lever/email), Screener + facts table, MinIO artifacts, dry-run.
- **Phase 3 — Frontend:** React+Vite+TanStack+TS+Bun — sources/keywords/thresholds
  config, review queue, manual-assist lane, credential management.

## 8. Risks & Mitigations

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | LLM fabricates resume content | KB-only guardrail (Q12) + error taxonomy (F2) + validation step on generated facts. |
| R2 | Wrong answer on disqualifying question | Facts table → gated inference → impediment queue (F3). |
| R3 | CAPTCHA/login walls | Lane downgrade; source drop (Q10). |
| R4 | Duplicate/re-posted opening applied twice | Ingestion dedup; never re-apply (F4). |
| R5 | PII leakage to external LLM | Redaction layer (Q14); company names accepted (F6). |
| R6 | Google blocks automated SSO login | Persistent browser session reuse, manual bootstrap (F7). |
| R7 | Silent connector death (session expiry) | Daily health checks + UI alert (F7). |
| R8 | Review queue staleness | 1-week TTL + manual close + source links (F8). |

## 9. Success Metrics (Q16, 30 days running)

- 500 openings collected/month; 100 applications submitted/month.
- ≥95% of auto-submitted applications at user-approvable quality (sampled).

## 10. Open Questions

- None. Requirements and stack frozen. Next artifact: Phase 1 implementation plan.

## 11. Stack (FROZEN — round "S" resolved)

### Backend / agent
- **Python + FastAPI** (S1 — BentoML rejected: no local model serving exists;
  the "model" is an HTTP call to OpenRouter).
- **PostgreSQL** (standard for the entire app, via S7/Infisical cascade) +
  SQLAlchemy/SQLModel + Alembic migrations.
- **Queue: DB-backed `jobs` table in Postgres + dedicated worker process**;
  scheduling via APScheduler (S2). No Redis — volume doesn't justify it
  (see estimate below).
- **Browser automation**: Playwright + `launch_persistent_context` (S3, F7).
- **PDF generation**: Jinja2 HTML/CSS → **WeasyPrint** (S4; revisit if output
  quality disappoints).
- **LLM**: OpenRouter gateway, two slots (S5):
  - *scoring* — cheapest model with reliable JSON-schema structured output
    (Gemini Flash / GPT-4o-mini class);
  - *tailoring* — one tier up (Claude Haiku class).
  - Estimated total cost: < US$5–10/month.
- **Email ingestion**: Gmail API, OAuth read-only scope (S6). App-dedicated
  label/filters minimum; a fully dedicated mailbox remains recommended.
- **Dedup similarity**: rapidfuzz on normalized (company, title) (S8);
  local embeddings only if false negatives appear.
- **Secrets vault**: Infisical self-hosted, dedicated service (S7) — backed by
  the shared Postgres.

### Frontend (Phase 3)
- React + Vite + TanStack + TypeScript + **Bun**.

### Infra
- Everything local via **Docker Compose**: `api`, `worker`, `postgres`,
  `minio`, `infisical`, `web` (Phase 3). Only LLM inference leaves the machine.

### Repo layout (S9 — monorepo, single GitHub repo)

```
lookout/
├── apps/
│   ├── api/        # FastAPI + agent modules
│   ├── worker/     # queue worker + scheduler (collector/matcher/tailor/applier)
│   └── web/        # frontend (Phase 3)
├── docs/           # this PRD + plans
└── docker-compose.yml
```

### Raw extraction volume estimate (S2 homework)

| Source group | Raw postings/day (est.) |
|---|---|
| Tier 0 APIs/RSS (RemoteOK, Remotive, Arbeitnow, Jobicy, WWR, WN, Himalayas, HN) | 200–500 |
| Tier 1 Greenhouse/Lever company list (50–200 cos) | 50–500 |
| Tier 2 BR/LatAm boards + Adzuna/Indeed queries | 200–700 |
| Tier 3 LinkedIn email alerts | 10–50 |
| **Total raw** | **~500–2,000/day → 15k–60k/month** |

After ingestion dedup: ~10k–40k/month. After deterministic pre-filter
(70–90% cut): **~1k–8k/month reach LLM scoring** — consistent with the 500
valid/month target (Q16). Sizing conclusions: DB-backed queue is comfortably
sufficient (peak ≈ a few jobs/minute); scoring cost stays within the
< US$5–10/month estimate.
