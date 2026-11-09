# Phase 2 Acceptance Walkthrough

Status: workflow implementation and regression verification passed; the final
complete-stack startup checks are in progress. This record will be updated with
observed results before acceptance is declared complete.

## Verification already completed — 2026-11-09

- Full suite: **332 passed**, two dependency deprecation warnings.
- Ruff lint passed; formatter check passed for **117 files**.
- Python wheel build passed.
- The 33 workflow/operational tests passed against real PostgreSQL 16 and MinIO.
- A binary object survived a MinIO container restart byte for byte.
- HTTP-stubbed inference plus real Chromium exercised API collection, deduplication,
  scoring, local identity resolution, form screening/filling, zero final POSTs,
  stored PDFs/answers/records, and integrity-checked artifact downloads.
- Recovery regressions cover a crash after submission, an obsolete worker lease,
  concurrent application processing, and final-record upload retries without
  repeating a completed submission.

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
