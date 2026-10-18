# Lookout

An AI agent that automatically applies to job openings on your behalf.
Primarily written in Python.

> Status: initial setup. Documentation will grow with the codebase.

## OpenCode setup

Agent configuration structure:

```
lookout/
├── opencode.jsonc          # Config: rules + Superpowers + MCPs (Context7, Playwright)
├── AGENTS.md               # General repository instructions
└── .opencode/
    ├── rules/              # Specific rules (.md files loaded automatically)
    │   ├── language.md     # Everything written in English
    │   ├── git-workflow.md # Conventional Commits + push at every major point
    │   ├── stack.md        # Stack and tooling (provisional, pending PRD)
    │   ├── privacy.md      # Personal data protection (data/ is gitignored)
    │   └── conventions.md  # Code conventions
    └── skills/             # Reusable skills (one folder per skill)
        └── skill-template/SKILL.md
```

- **Rules**: add any `.md` to `.opencode/rules/` — it takes effect on the next
  message exchange, no config changes needed.
- **Skills**: each skill is a folder with a `SKILL.md` (frontmatter with `name`
  and `description`). Docs: https://opencode.ai/v2/docs/skills
- **Superpowers** (plugin): registers methodology skills (brainstorming,
  writing-plans, TDD, systematic-debugging...). Requires restarting OpenCode
  after setup. Verify by asking: "Tell me about your superpowers".
- **Context7** (MCP): up-to-date library documentation. Works anonymously;
  for higher rate limits set the `CONTEXT7_API_KEY` env var and enable the
  commented header in `opencode.jsonc`. Verify with `opencode mcp list`.
- **Playwright** (MCP): browser automation for prototyping and testing
  job-board flows. First use may require `npx playwright install chromium`.
