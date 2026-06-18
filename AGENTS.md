# AGENTS.md

## Skills

- Shared Agent Skills live in `.agents/skills`; do not copy their full content here.
- OpenCode: load the relevant skill before implementation.
- Codex or other agents: read `.agents/skills/<skill>/SKILL.md` and referenced files.
- Use:
  - `grill-me` when requirements are unclear.
  - `to-prd` to turn agreed requirements into a PRD.
  - `to-issues` to break plans into vertical slices.
  - `tdd` for red-green-refactor implementation.
  - `diagnose` for bugs, failing tests, and regressions.
  - `zoom-out` for unfamiliar code.
  - `improve-codebase-architecture` for deeper refactors.
  - `triage` for issue workflows.

## Project Context

- This repository is implementing **RepoLens MCP v0.1**.
- The active implementation branch is `feature/repolens-v0.1`.
- Work is organized as GitHub issue slices under the v0.1 umbrella tracker.
- Each implementation branch should target exactly one issue or explicitly approved sub-issue.
- Keep v0.1 scope local-first, deterministic, and safe by default.
- Do not add AI/LLM-required graph generation, embeddings, telemetry, hosted services, browser UI, HTTP API, write-capable MCP tools, or runtime network calls during indexing.

## Repo Shape

- Python package source lives under `src/repolens`.
- Tests live under `tests`.
- The CLI command is `repolens`.
- Project metadata is in `pyproject.toml`.
- Dependency/environment management uses `uv`.
- `uv.lock` should be committed.
- `.venv/` must not be committed.
- RepoLens generated artifacts live under `.repolens/` and must not be committed.
- `.repolens/` is local cache/output, not source.

## Runtime And Tooling

- Python baseline is `>=3.11`.
- Use `uv` for project commands.
- Do not assume bare `python`, `pytest`, `ruff`, or `mypy` points at the correct environment.
- Prefer `uv run ...` commands.

## Common Commands

Set up or refresh the environment:

```bash
uv sync
```

Run the full verification gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

Run the CLI:

```bash
uv run repolens --help
uv run repolens status .
uv run repolens index <fixture-or-repo-path>
```

Check that read-like status does not mutate the repo:

```bash
test ! -d .repolens && echo "OK: status did not mutate repo"
```

## Workflow

- Start each issue from the updated feature branch:

```bash
git checkout feature/repolens-v0.1
git pull --ff-only origin feature/repolens-v0.1
git checkout -b slice/<issue-number>-<short-name>
```

- Use one fresh OpenCode session per issue slice.
- Give the assistant the GitHub issue plus the project-specific prompt.
- Keep the assistant inside the current issue scope.
- Do not let an implementation slice pull in future issue behavior.
- Use TDD where practical: one behavior, one test, one implementation step.
- Run the full verification gate before committing.
- Open PRs into `feature/repolens-v0.1`, not `main`.
- After merge:
  - close the completed issue,
  - update the umbrella tracker,
  - delete merged local/remote slice branches,
  - start the next slice from fresh `feature/repolens-v0.1`.

## Commit And PR Conventions

Use concise area-prefixed commit messages:

```bash
cli: scaffold repolens status (#3)
scanner: add safe repository discovery (#4)
graph: add deterministic store and exports (#5)
python: index source structure (#6)
js-ts: index imports and packages (#7A)
js-ts: index symbols and exports (#7B)
js-ts: resolve simple aliases and harden exports (#7C)
```

PR descriptions should include:

- Summary.
- What changed.
- Verification commands.
- Scope notes.
- `Closes #<issue>` only when the whole issue is complete.
- Use `Refs #<issue>` or `Part of #<issue>` for sub-issues.

## Generated Files And Ignore Rules

Do not commit:

```text
.venv/
.repolens/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
build/
```

Commit when relevant:

```text
uv.lock
pyproject.toml
src/repolens/...
tests/...
docs/...
README.md
AGENTS.md
```

## RepoLens Safety Rules

- Scanner/indexing behavior must stay inside the provided analysis root.
- Paths in graph artifacts should be repo-relative POSIX paths.
- Never scan `.repolens`.
- Skip secret-looking files by path/name before parsing.
- Do not store secret contents.
- Do not mirror full source code into AI-facing artifacts.
- Candidate commands may be detected and recorded, but must not be executed.
- Deploy/publish-like commands must not be recommended for automatic execution.
- Runtime package registry lookups are out of scope for v0.1.

## Architecture Notes

- Keep CLI handlers thin.
- Put behavior in application/service modules.
- Reuse scanner, graph store, and exporter pipelines instead of duplicating traversal logic.
- Extractors should read only scanner-approved files.
- Parsers must not execute or import analyzed project code.
- Store deterministic facts in SQLite and deterministic exports.
- Line numbers may be metadata, not primary identity.
- IDs should be stable across normal line shifts where practical.

## Current v0.1 Progress

Completed or split-completed:

- #3 Installable CLI Scaffold With Missing-Graph Status.
- #4 Safe Repository Discovery And Artifact Bootstrap.
- #5 Deterministic Graph Store And Exports.
- #6 Python Structure Indexing End To End.
- #7 JavaScript And TypeScript Structure Indexing End To End, completed through sub-slices:
  - #7A JS/TS Imports And Package Classification.
  - #7B JS/TS Symbols, Exports, And CommonJS Facts.
  - #7C TypeScript Alias Resolution And Export Hardening.
- #8 Config, Command, Package, And Entrypoint Indexing.
- #9 Markdown, Comments, Docs, And Agent Guidance Indexing.

Next planned slice:

- #10 Incremental Update And Staleness Classification.

## Architecture-Level Context

- If `CONTEXT.md` exists, read it before naming new concepts.
- If `docs/adr/` exists, read relevant ADRs before architecture-level changes.
- Do not re-litigate accepted decisions unless new implementation friction justifies it.

