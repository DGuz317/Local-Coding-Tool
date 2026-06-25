# RepoLens v0.2 Planning Interview Summary Archive

Status: archived historical decision log.

Date: 2026-06-18

Source plan: `docs/repolens-v0.2-plan.md`

## Initial Codebase Findings

- v0.1 already had MCP envelopes, missing-graph responses, ambiguity handling, impact and reading-order heuristics, status freshness, schema checks, update change classes, and safety tests.
- v0.1 did not yet have a repo-wide canonical graph hash or graph validation service.
- Edge payloads exposed generic metadata but not first-class `confidence`, `evidence`, or `resolution_strategy`.
- Python imports were classified but not resolved to local module files.
- JS/TS had simple TypeScript alias resolution but unresolved relative `./` and `../` imports.

## Locked Decisions

- v0.2 is a reliability-hardening release, not broad feature expansion.
- Release gate requires P0 hardening, full verification, self-dogfooding, Python/JS/TS/mixed fixture coverage, and known limitations.
- Tree-sitter remains non-blocking and experimental.
- Canonical graph hash excludes timestamps, mtimes, raw/normalized file hashes, absolute paths, and line-only evidence.
- Edge `confidence`, `evidence`, and `resolution_strategy` become first-class Edge Contract fields.
- Duplicate logical edges use `(source_id, target_id, kind)` identity and merge evidence/strategies.
- Graph validation failures abort before replacing artifacts and preserve the previous graph.
- v0.2 keeps rebuild-on-incompatibility and does not add a SQLite migration framework.
- Python resolver scope is deterministic local resolution only.
- JS/TS resolver scope is relative imports plus simple deterministic aliases.
- Low-confidence fuzzy matches are candidates only and must not become graph edges.
- Impact Analysis is graph-derived edit-planning context, not runtime certainty.
- MCP standardizes the existing v0.1-compatible envelope rather than replacing it.
- Selective Update is file-level replacement, not symbol-level mutation.
- Large performance fixtures are generated deterministically, not committed as large fixture trees.
- Redaction preserves useful paths, package names, and symbol names while protecting obvious secrets.
- Package Boundary detection requires explicit deterministic package/config evidence.
- Dogfooding commits reports, distilled fixtures, and known limitations, not vendored third-party snapshots.
- Minimal CI is release-blocking: Ruff check, Ruff format check, mypy, pytest, package build, and isolated install smoke.

## Issue Implications

- Reword issues as hardening and normalization where v0.1 already had partial behavior.
- Add graph validation and canonical hash before deeper resolver or MCP polish work.
- Add Edge Contract storage before query/API polish.
- Split Python local import resolution from JS/TS relative import resolution.
- Keep parser abstraction and Tree-sitter out of the release-blocking path unless dogfooding proves otherwise.
