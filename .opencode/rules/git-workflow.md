# GitHub Sync

Whenever the project reaches a **major point**, update the GitHub repository.

## What counts as a major point

- A complete, verified feature (builds and tests pass)
- A relevant bug fix
- A milestone/deliverable agreed with the user
- A finished refactor that changes the project structure

## Required workflow

1. Check `git status` and review the changes with `git diff`.
2. Before committing, make sure the project builds and the **full test suite**,
   lint, and formatter check pass. For Python, run `pytest`, `ruff check .`, and
   `ruff format --check apps tests` from the repository root; do not limit
   verification to tests for the current task. The formatter gate covers
   application and test code; do not reformat generated Alembic files or docs.
3. If formatting fails, run `ruff format apps tests`; fix all test and lint
   failures, then rerun the checks until they pass.
4. Create one commit per milestone using Conventional Commits (see below).
5. Before every push, confirm the full test suite, lint, and formatter check
   have passed since the latest code change. Reuse successful results for the
   unchanged tree; do not rerun checks solely because a push is next. If code
   changes after verification, rerun the checks and fix any failures before
   pushing.
6. Run `git push` of the current branch to the GitHub remote.

## Commit messages — Conventional Commits (always in English)

Format:

```
<type>: <what was done>
```

- **Allowed types**:
  - `feat` — new feature
  - `fix` — bug fix
  - `docs` — documentation only
  - `style` — formatting, no logic change
  - `refactor` — code change that neither fixes a bug nor adds a feature
  - `test` — adding or fixing tests
  - `chore` — maintenance, tooling, setup
  - `perf` — performance improvement
  - `build` — build system or dependencies
  - `ci` — CI configuration
- **The description is always written in English**, in the imperative mood,
  short, with no period at the end.
- Optional scope in parentheses: `feat(scraper): handle pagination`.
- Examples:
  - `feat: add job board scraping pipeline`
  - `fix: handle expired session tokens during login`
  - `docs: document the application flow`
  - `chore: initial project setup`

## Conditions and limits

- If the directory is **not a git repository yet** or **has no remote configured**,
  tell the user and offer to initialize it (`git init`, `git remote add origin <url>`)
  before proceeding.
- **Never** commit secrets or sensitive files (`.env`, keys, credentials, tokens).
  Check the `.gitignore` before the first commit.
- Do not commit auto-generated files (build outputs, dependencies, caches).
- If the working tree has changes unrelated to the milestone, commit only the
  milestone's scope.
