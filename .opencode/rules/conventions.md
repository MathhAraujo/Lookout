# Conventions

> Base rule. Any `.md` file in `.opencode/rules/` loads automatically as
> persistent instructions (via `opencode.jsonc`).

- Before finishing a task, verify that the changes build and pass the tests.
- Keep functions small and focused; prefer explicit names over comments.
- Handle errors explicitly — an automation agent must never fail silently
  (log and surface failures, e.g. a failed job application).
- <!-- TODO: add naming, folder structure and style conventions as the codebase grows -->
