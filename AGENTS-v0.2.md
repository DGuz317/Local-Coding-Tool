# AGENTS.md

## Skills

- Shared Agent Skills live in `.agents/skills`; do not copy their full content here.
- OpenCode: load the relevant skill before implementation.
- Codex or other agents: read `.agents/skills/<skill>/SKILL.md` and referenced files.
- Use:
  - `grill-with-docs` when requirements are unclear (upgrade version of `grill-me`).
  - `to-prd` to turn agreed requirements into a PRD.
  - `to-issues` or `to-issue` to break plans into vertical GitHub issue slices, depending on the installed skill name.
  - `tdd` for red-green-refactor implementation.
  - `diagnose` for bugs, failing tests, and regressions.
  - `zoom-out` for unfamiliar code.
  - `improve-codebase-architecture` for deeper refactors.
  - `triage` for issue workflows.

## Project Context

- This repository is implementing **RepoLens MCP v0.2**.
- v0.2 is a reliability-hardening release over v0.1, not a rewrite.
- Release theme:

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

- The active implementation branch is `feature/repolens-v0.2`.
- Work is organized as GitHub issue slices under the v0.2 umbrella tracker.
- Each implementation branch should target exactly one issue or explicitly approved sub-issue.
- Keep v0.2 local-first, deterministic, safe by default, and compatible with the v0.1 product contract where possible.
- Preserve these v0.1 guarantees unless an approved v0.2 issue explicitly changes them:
  - local `.repolens` artifacts,
  - SQLite as the authoritative graph store,
  - deterministic exports,
  - read-only MCP tools,
  - no required AI model,
  - no required embeddings,
  - no hosted sync,
  - no telemetry,
  - no runtime network dependency for normal indexing or MCP serving,
  - no write-capable MCP tools.
- Do not add cloud services, browser UI, HTTP API, PR bot behavior, automatic code editing, required vector databases, required Tree-sitter, or runtime package-registry lookups during indexing.

## v0.2 Scope Priorities

P0 release blockers:

1. Roadmap and release criteria.
2. Edge Contract storage and duplicate edge normalization.
3. Canonical Graph Hash, Graph Validation, and rebuild guardrails.
4. Python local import resolution.
5. JS/TS relative import resolution and deterministic alias hardening.
6. Resolution Strategy normalization and candidate-only ambiguity handling.
7. Related Test relationships with confidence and evidence.
8. Impact Analysis grouping and Target Expansion traversal boundaries.
9. Suggested Reading Order ranking and command context.
10. Shared MCP envelope foundation and contract tests.
11. MCP tool migration to standardized envelopes, errors, pagination, and stdio discipline.
12. File-level Selective Update planner and graph replacement path.
13. Selective Update cleanup tests and generated benchmark fixture.
14. Shared Redaction Policy and scanner/security fixtures.
15. MCP No Whole-Source Disclosure and raw text safety tests.
18. Dogfooding reports and regression fixture process.
19. Minimal CI and isolated install smoke.
20. v0.2 user docs, assistant docs, release checklist, and known limitations.

Non-blocking P1 unless dogfooding promotes them:

- #16 Package Boundary, workspace, and command grouping awareness.
- #17 Optional Parser Backend experiment behind default-stable behavior.

## Repo Shape

- Python package source lives under `src/repolens`.
- Tests live under `tests`.
- Project docs live under `docs`.
- ADRs, when present, live under `docs/adr`.
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

Run package/build verification when release readiness or CI work touches packaging:

```bash
uv build
```

Run the CLI:

```bash
uv run repolens --help
uv run repolens status .
uv run repolens index <fixture-or-repo-path>
uv run repolens update <fixture-or-repo-path>
```

Check that read-like status does not mutate the repo:

```bash
test ! -d .repolens && echo "OK: status did not mutate repo"
```

Run focused tests while developing a slice:

```bash
uv run pytest tests/<test-file>.py -q
```

## Workflow

- Start each issue from the updated v0.2 feature branch:

```bash
git checkout feature/repolens-v0.2
git pull --ff-only origin feature/repolens-v0.2
git checkout -b slice/<issue-number>-<short-name>
```

- Use one fresh OpenCode session per issue slice.
- Give the assistant the GitHub issue plus this `AGENTS.md` context.
- Keep the assistant inside the current issue scope.
- Do not let an implementation slice pull in future issue behavior.
- Use TDD where practical: one behavior, one test, one implementation step.
- Run the full verification gate before committing.
- Open PRs into `feature/repolens-v0.2`, not `main`.
- After merge:
  - close the completed issue,
  - update the v0.2 umbrella tracker,
  - delete merged local/remote slice branches,
  - start the next slice from fresh `feature/repolens-v0.2`.

## Commit And PR Conventions

Use concise area-prefixed commit messages:

```bash
graph: add edge contract fields (#2)
graph: add canonical graph validation (#3)
resolver: resolve python local imports (#4)
resolver: resolve js-ts relative imports (#5)
resolver: normalize resolution strategies (#6)
graph: store related test relationships (#7)
mcp: group impact analysis results (#8)
mcp: improve reading order reasons (#9)
mcp: add shared response envelope (#10)
mcp: migrate tools to envelope contract (#11)
update: add selective update planner (#12)
update: add cleanup and benchmark fixtures (#13)
security: add redaction policy (#14)
security: prove no whole-source disclosure (#15)
workspace: improve package boundaries (#16)
parser: add optional backend interface (#17)
dogfood: add v0.2 regression reports (#18)
ci: add minimal release gate (#19)
docs: add v0.2 assistant usage guide (#20)
```

PR descriptions should include:

- Summary.
- What changed.
- Verification commands.
- Scope notes.
- Known limitations or deferred behavior.
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
- Redact secret-like metadata and command strings before storage or output.
- Do not mirror full source code into AI-facing artifacts or MCP responses.
- `search_text` may read scanner-approved live text, but must return only bounded sanitized previews.
- Candidate commands may be detected and recorded, but must not be executed.
- Verification commands must be labeled as candidates and not run unless the user or developer explicitly runs them outside RepoLens.
- Deploy/publish-like commands must not be recommended for automatic execution.
- Runtime package registry lookups are out of scope for v0.2.
- MCP remains read-only in v0.2.
- MCP tools must not update graphs, modify files, execute commands, or expose whole source files.

## Architecture Notes

- Keep CLI handlers thin.
- Put behavior in application/service modules.
- Reuse scanner, graph store, query, and exporter pipelines instead of duplicating traversal logic.
- Extractors should read only scanner-approved files.
- Parsers must not execute or import analyzed project code.
- Store deterministic facts in SQLite and deterministic exports.
- Line numbers may be metadata, not primary identity.
- IDs should be stable across normal line shifts where practical.
- v0.2 Edge Contract fields should make trust and provenance explicit:
  - `confidence`,
  - `resolution_strategy`,
  - bounded normalized `evidence` JSON.
- Duplicate logical edges should merge by `(source_id, target_id, kind)` and aggregate evidence deterministically.
- Low-confidence fuzzy matches must remain candidates only and must not be stored as graph edges.
- Impact Analysis is edit-planning context, not runtime certainty.
- Target Expansion may use containment in bounded ways, but impact traversal must not climb upward through containers and explode into siblings.
- Candidate Verification Commands must not imply commands were run or should be run automatically.
- MCP success responses should use the shared v0.1-compatible envelope with `ok`, `data`, `warnings`, `limits`, `confidence`, `evidence`, `freshness`, and `truncation`; include `pagination` where applicable.
- MCP expected failures should use structured `ok: false` errors.
- MCP stdio mode must not write logs or progress to stdout.

## v0.2 Issue Dependency Notes

- #2 Edge Contract should happen before graph validation, resolver, impact, and MCP evidence work.
- #3 Canonical Graph Hash and Graph Validation should happen before deeper resolver and selective update work.
- #10 MCP envelope foundation should happen before MCP tool migration, but it does not need to wait for impact analysis or reading order.
- #11 MCP tool migration depends on impact analysis, reading order, and the shared envelope foundation.
- #14 Redaction/Security core can happen before MCP no-source-disclosure proof.
- #15 MCP No Whole-Source Disclosure depends on MCP envelope foundation and redaction/security core.
- #18 Dogfooding does not block on P1 package/workspace work.
- #19 Minimal CI should start early after the v0.2 roadmap issue exists and expand as fixture coverage stabilizes.
- #20 Docs and release readiness should absorb final MCP contracts and dogfooding findings.

## Dogfooding And Regression Rules

- Dogfood RepoLens on this repository plus at least one representative Python repo, one JS/TS repo, and one mixed docs/config repo.
- Do not vendor third-party repository snapshots into this repo.
- Commit dogfooding reports, known limitations, and distilled regression fixtures.
- Convert every actionable dogfooding bug into a regression fixture or a documented deferral.
- Track false positives, false negatives, update performance, resolver misses, MCP UX friction, and security/sanitization gaps.

## Architecture-Level Context

- If `CONTEXT.md` exists, read it before naming new concepts.
- If `docs/repolens-v0.2-planning-interview-summary.md` exists, treat it as the v0.2 decision log.
- If `docs/repolens-v0.2-issue-breakdown.md` exists, use it as the active v0.2 backlog source.
- If `docs/adr/` exists, read relevant ADRs before architecture-level changes.
- Do not re-litigate accepted decisions unless new implementation friction justifies it.
