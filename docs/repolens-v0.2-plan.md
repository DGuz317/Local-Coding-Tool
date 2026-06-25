# RepoLens MCP v0.2 Plan Archive

Status: archived historical plan.

Version: Draft 1

Date: 2026-06-18

Scope: upgrade path from RepoLens MCP v0.1 to v0.2.

## Theme

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

## Positioning

v0.2 hardened the v0.1 local-first graph system instead of rewriting it. The release preserved local `.repolens` artifacts, SQLite as the authoritative store, deterministic exports, read-only MCP tools, no required AI model, no embeddings, and no runtime network dependency for normal indexing or serving.

## Goals

- Improve graph trust through evidence, confidence, validation, and schema stability.
- Improve deterministic reference resolution for Python, JS, TS, docs, configs, packages, tests, and entrypoints.
- Improve impact analysis and suggested reading order before editing.
- Polish MCP responses so assistants consume RepoLens output predictably.
- Make update/status behavior faster and more accurate on real repositories.
- Harden privacy and safety for paths, secrets, command strings, raw search, and artifacts.
- Add enough dogfooding, CI, and docs to make the release repeatable.

## Non-Goals

- No cloud dashboard, hosted sync, telemetry, browser UI, automatic code editing, or PR bot behavior.
- No write-capable MCP tools.
- No required embeddings or vector database.
- No Kuzu migration.
- No full CFG, data-flow analysis, taint analysis, deep semantic call graph, full TypeScript compiler resolution, or full framework route extraction.

## Release Themes

| Priority | Theme | Outcome |
|---|---|---|
| P0 | Graph correctness and schema stability | Graph facts are stable, validated, and explainable. |
| P0 | Better reference resolution | More imports, packages, paths, tests, and symbols resolve deterministically. |
| P0 | Impact and reading-order quality | Assistants get better pre-edit context with evidence and reasons. |
| P0 | MCP contract polish | Tools return consistent, capped, evidence-backed responses. |
| P0 | Incremental update correctness | `update` and `status` become faster and more accurate. |
| P0 | Security/privacy hardening | Artifacts and MCP output are safer for real repositories. |
| P1 | Parser abstraction | Optional Tree-sitter can be tested without changing defaults. |
| P1 | Package/workspace awareness | Monorepos and multi-package projects are represented more clearly. |
| P0 | Dogfooding and CI | Real-repo bugs become fixtures and the release gate is repeatable. |

## Milestones

1. Planning and backlog: publish tracker, labels, vertical slices, release criteria, and dogfooding targets.
2. Graph correctness foundation: validation, schema compatibility, edge/evidence normalization, graph diff, and stable IDs.
3. Resolution, impact, and MCP polish: import resolution, strategy metadata, impact grouping, reading-order reasons, and MCP envelopes.
4. Update performance and security hardening: selective update, stale detection, cleanup tests, redaction, containment, and search safety.
5. Parser abstraction and package awareness: optional backend interface plus explicit package/workspace evidence.
6. Dogfooding, CI, docs, and release candidate: self-dogfood, fixtures, CI smoke, README/docs, release notes, and known limitations.

## Release Acceptance

- `index` and `update` are deterministic on fixture repositories.
- `status` remains read-like and does not mutate artifacts.
- Graph schema compatibility and validation run before artifact replacement.
- Reference resolution includes strategy, confidence, evidence, and candidate-only ambiguity handling.
- Impact analysis and reading order are evidence-backed and bounded.
- MCP tools use consistent envelopes, caps, truncation, pagination, and stale/missing graph responses.
- Raw text search is sanitized and capped.
- Secret-looking files are skipped before parsing.
- Command strings are sanitized and marked as not run.
- Optional Tree-sitter does not affect default install.
- CI passes lint, format check, typecheck, tests, and build.
- Dogfooding report and known limitations are complete.
