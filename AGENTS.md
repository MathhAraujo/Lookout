# Lookout — Project Instructions

> Persistent instructions for AI agents working on this repository.

## About the project

Lookout is an AI agent that automatically applies to job openings on behalf of the user. The codebase is primarily **Python**.

## OpenCode setup structure

- `opencode.jsonc` — project config: loads rules from `.opencode/rules/`, the Superpowers plugin (methodology skills) and the Context7 MCP server (library docs).
- `AGENTS.md` — this file: general repository guidance.
- `.opencode/rules/` — specific rules (language, git workflow, stack, privacy, conventions). `.md` files here load automatically.
- `.opencode/skills/` — reusable skills. Each skill is a folder with a `SKILL.md` and frontmatter with `name` and `description`.

## General rules

- All code, comments, documentation and commit messages are written in **English**, even when the conversation is in pt-br (see `.opencode/rules/language.md`).
- Keep changes consistent with existing code style and patterns.
- Do not edit auto-generated files.
- Stack, tooling and build/test commands: see `.opencode/rules/stack.md`.
