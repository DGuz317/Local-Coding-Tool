# AGENTS.md

## Skills

- Shared Agent Skills live in `.agents/skills`; do not copy their full content here.
- OpenCode: load the relevant skill before implementation.
- Codex or other agents: read `.agents/skills/<skill>/SKILL.md` and referenced files.
- Use:
  - `grill-with-docs` when requirements are unclear (upgrade version of `grill-me`).
  - `to-prd` to turn agreed requirements into a PRD.
  - `to-issues` to break plans into vertical slices.
  - `tdd` for red-green-refactor implementation.
  - `diagnose` for bugs, failing tests, and regressions.
  - `zoom-out` for unfamiliar code.
  - `improve-codebase-architecture` for deeper refactors.
  - `triage` for issue workflows.

## Project Context

- This repository is implementing **RepoLens MCP v0.3**.
- v0.3 theme: **Make RepoLens the assistant's context budget manager.**
- The active release integration branch is `feature/repolens-v0.3`.
- The GitHub umbrella tracker is `#79`.
- Work is organized as issue slices `#80` through `#90`.
- Each implementation branch should target exactly one issue or explicitly approved sub-issue.
- Keep v0.3 focused on task-scoped Context Packs and assistant context economy.
- Do not add AI/LLM-required graph generation, embeddings, telemetry, hosted services, browser UI, HTTP API, write-capable MCP tools, automatic code editing, or runtime network calls during indexing.

## v0.3 Product Boundary

Context Packs are the primary v0.3 product surface.

A Context Pack is:

- deterministic;
- stateless;
- task-scoped;
- bounded by explicit item and character budgets;
- graph-derived;
- file-centric;
- evidence-backed;
- orientation-only;
- safe for assistant-facing MCP and CLI output.

A Context Pack is not:

- a source preview bundle;
- a full context dump;
- an AI-generated semantic summary;
- an embedding/vector search result;
- a runtime reachability claim;
- a persisted assistant session;
- a write/edit plan;
- proof that lower-priority context is irrelevant.

## Repo Shape

- Python package source lives under `src/repolens`.
- Tests live under `tests`.
- Docs live under `docs`.
- ADRs live under `docs/adr`.
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

Run the existing CLI:

```bash
uv run repolens --help
uv run repolens status .
uv run repolens index <fixture-or-repo-path>
uv run repolens report <fixture-or-repo-path>
```

Run v0.3 CLI surfaces after their slices land:

```bash
uv run repolens context <fixture-or-repo-path> "Fix the auth timeout bug" --json
uv run repolens evaluate-context <fixture-or-repo-path> --json
```

Check that read-like status does not mutate the repo:

```bash
test ! -d .repolens && echo "OK: status did not mutate repo"
```

## v0.3 Issue Order

Follow the release tracker unless a maintainer explicitly changes the dependency order.

Release-blocking P0 path:

1. `#80` Context Pack contracts and fixture specification.
2. `#81` Context Pack tracer bullet.
3. `#82` Context Pack safety and ambiguity hardening.
4. `#83` Evidence-gated support groups.
5. `#84` Derived Structural Summaries and package ownership.
6. `#85` Pack-scoped expansion and relevance.
7. `#86` Context Pack Evaluation execution.
8. `#87` v0.3 docs and release readiness.

Non-blocking P1 follow-ups:

- `#88` Navigation gap improvements from evaluation.
- `#89` Persisted summary caching if needed.
- `#90` Additional evaluation corpora.

Do not start P1 work until the release-blocking Context Pack path has enough implementation and evaluation evidence to justify it.

## Workflow

Start each issue from the updated release branch:

```bash
git checkout feature/repolens-v0.3
git pull --ff-only origin feature/repolens-v0.3
git checkout -b slice/<issue-number>-<short-name>
```

Implementation workflow:

- Use one fresh OpenCode session per issue slice.
- Give the assistant the GitHub issue plus this file.
- Read `CONTEXT.md` before naming or redefining product concepts.
- Read relevant ADRs before architecture-level changes.
- Keep the assistant inside the current issue scope.
- Do not let an implementation slice pull in future issue behavior.
- Use TDD where practical: one behavior, one test, one implementation step.
- Run the full verification gate before committing.
- Open PRs into `feature/repolens-v0.3`, not `main`.
- After merge:
  - close the completed issue only when all acceptance criteria are satisfied;
  - update `docs/repolens-v0.3-release-tracker.md` when issue references or release evidence change;
  - delete merged local/remote slice branches;
  - start the next slice from fresh `feature/repolens-v0.3`.

## Commit And PR Conventions

Use concise area-prefixed commit messages:

```bash
context-pack: add schema contract (#80)
context-pack: add deterministic pack id (#81)
security: add no-source-disclosure guard (#82)
context-pack: add evidence-gated test support (#83)
summary: derive file structural summaries (#84)
mcp: add expand context tool (#85)
evaluation: add context fixture runner (#86)
docs: add v0.3 context workflow guide (#87)
```

PR descriptions should include:

- Summary.
- What changed.
- Why it changed.
- How it affects the existing flow.
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
docs/adr/...
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
- Runtime package registry lookups are out of scope.

## v0.3 Context Pack Safety Rules

Context Pack MCP and CLI output must pass through the central No Whole-Source Disclosure guard.

Never expose through Context Packs, expansion, relevance explanation, evaluation output, logs, handles, or task fingerprints:

- full source files;
- source snippets;
- code bodies;
- function or method signatures;
- paragraph excerpts;
- raw comment text;
- raw Agent Guidance instruction text;
- raw secret-like task text or focus hints;
- absolute host paths;
- serialized source-derived payloads.

Allowed orientation metadata includes:

- repo-relative file paths;
- structural symbol names, kinds, qualified names, exported/public classification where known, and line ranges;
- package/workspace ownership when explicit evidence exists;
- relationship kinds;
- confidence categories;
- bounded evidence metadata;
- freshness/hash metadata;
- capped command metadata marked not run;
- tiny Agent Guidance metadata such as path, kind, freshness, and reason.

Risk Signals should include metadata only: location, category, reason, confidence, evidence, and freshness. They must not include raw comment text.

Human output should use softer wording such as `lower-priority context to inspect later`. Do not tell assistants that a file is irrelevant, safe to ignore, or guaranteed unaffected.

## Context Pack Contract Guidance

When implementing or modifying Context Pack behavior, preserve these properties:

- `context_pack_id` is deterministic and must not leak raw task text, secret-like text, absolute paths, source snippets, or session state.
- Item handles are deterministic and pack-scoped.
- Expansion handles must only refer to items returned in the pack.
- Pack IDs and handles should derive from canonical graph state, Context Pack version, normalized/redacted task fingerprint, focus hints, and budget parameters.
- Stale or mismatched pack IDs should return structured `ok: false` errors requiring a fresh pack.
- Ranking must use deterministic inputs and stable tie-breakers.
- Broad tasks must return bounded packs with breadth warnings, not repository dumps.
- No-match tasks should return successful low-confidence packs with no broad dump.
- Ambiguous targets should return candidates instead of silently choosing one.
- Invalid focus paths outside the analysis root are errors.
- In-root unresolved focus hints are warnings that lower confidence.

Default Context Pack output should prioritize:

1. freshness, warnings, and structured recoverable errors;
2. First-Read Files;
3. ambiguity candidates;
4. likely tests;
5. risk signals;
6. configs and candidate verification commands;
7. docs;
8. tiny Agent Guidance metadata;
9. lower-priority context.

Support groups must be evidence-gated and capped. They must not crowd out First-Read Files unless the task is explicitly about that support group, such as a test-focused task.

## Structural Summary Guidance

Structural Summaries should:

- be derived from graph facts at query time unless an issue explicitly adds justified caching;
- avoid generated prose that sounds more certain than the graph evidence;
- avoid source excerpts;
- include freshness/hash metadata where applicable;
- summarize structure for repository, package/workspace, directory, file, symbol, or test-group scopes only when useful for a Context Pack.

Package Boundary ownership must come from explicit package/config evidence. Do not infer package ownership from conventional directory names alone.

## MCP And CLI Guidance

- MCP behavior remains read-only.
- MCP tools must use the standard response envelope with data, freshness, warnings, limits, and truncation metadata.
- CLI handlers should stay thin and delegate to framework-independent services.
- `get_task_context` and `repolens context` must use the same Context Pack service.
- `expand_context` and `explain_relevance` must be stateless and validate Context Pack IDs against current graph freshness/hash.
- `expand_context` should default to depth 1 and must enforce a hard maximum depth of 2.
- Expansion and relevance responses must include reasons, confidence, evidence, freshness metadata, limits, and truncation state.
- Candidate Verification Commands are not recommendations to execute; mark them as not run.

## Evaluation Guidance

`repolens evaluate-context` should prove whether Context Packs improve assistant orientation.

Release-blocking evaluation should cover:

- direct symbol tasks;
- config-driven tasks;
- ambiguous tasks;
- broad tasks;
- no useful match tasks;
- stale graph warnings;
- invalid outside-root focus paths;
- unresolved in-root focus hints;
- secret-like task redaction;
- stale pack ID errors;
- no-snippet enforcement.

Evaluation metrics should include:

- first-read hit rate;
- irrelevant file count;
- test inclusion;
- pack size;
- expansion count;
- safety negative outcomes.

Evaluation should compare Context Packs against existing `suggest_reading_order` and a simple lexical baseline.

Use expectation-based release gates rather than universal numeric thresholds.

## Architecture Notes

- Keep CLI handlers thin.
- Put behavior in application/service modules.
- Reuse scanner, graph store, query service, and exporter pipelines instead of duplicating traversal logic.
- Extractors should read only scanner-approved files.
- Parsers must not execute or import analyzed project code.
- Store deterministic facts in SQLite and deterministic exports.
- Line numbers may be metadata, not primary identity.
- IDs should be stable across normal line shifts where practical.
- Context Pack code should be deterministic under repeated runs against the same graph, task, focus hints, and budget parameters.

## Architecture-Level Context

- If `CONTEXT.md` exists, read it before naming new concepts.
- If `docs/adr/` exists, read relevant ADRs before architecture-level changes.
- `docs/adr/0003-v0-3-context-pack-boundary.md` defines the v0.3 Context Pack boundary.
- Do not re-litigate accepted decisions unless new implementation friction justifies it.

