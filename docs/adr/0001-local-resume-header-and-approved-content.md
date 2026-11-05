# ADR-0001: Local resume header and approved body selection

Status: Accepted (2026-11-05)

## Context

The candidate wants to tailor a base resume while keeping the personal header
fixed. Header data is unnecessary for relevance selection and must not enter
external inference. Literal validation of model-authored prose also conflicts
with translating a resume into a different posting language.

## Decision

- Keep `identity.md` separate from professional `ResumeContent`. Load identity
  locally for privacy checks and final rendering, never for prompt serialization.
- Give the model only professional body facts and the redacted posting.
- Accept a strict `ResumeSelection`: language, exact experience/project IDs,
  zero-based highlight indices, and approved skills. Reject extra fields.
- Resolve every selection to approved local text. The summary, education, and
  languages are permanent; header values are never model-controlled.
- Store user-approved body translations under `translations/<language>/`, sharing
  the root identity. Missing translations fail before inference.
- Reject accidental personal data in body files; redact known identity variants
  and phone/CPF/email patterns in the posting as defense in depth.
- Publish PDFs atomically so renderer failures preserve the last valid artifact.

## Consequences

Relevance ordering and selection remain automated. All displayed facts and
translations come from user-approved local content. Arbitrary model-authored
rewrites and automatic translation are intentionally excluded from Phase 1;
users maintain the approved body in each supported language. Privacy scanning is
a backstop, not a substitute for keeping personal data out of professional files.
