---
name: Skill Template
description: ""
metadata:
  opencode/autoinvoke: false
---

# Skill Template

> Template for creating new skills in `.opencode/skills/`.
> Copy this folder, rename it to the desired ID (kebab-case) and fill in the frontmatter.

## How it works

- The folder name defines the skill ID (e.g. `.opencode/skills/my-skill/SKILL.md` → ID `my-skill`).
- `name` is only the display label.
- `description` is what makes the skill appear in the agent's available list.
  Without a `description` (or with `opencode/autoinvoke: false`), the skill is
  not advertised automatically, but can still be loaded explicitly by ID.

## Skill body

Put the instructions here: workflow steps, commands, and references to
supporting files (scripts, templates) kept next to the `SKILL.md`.
