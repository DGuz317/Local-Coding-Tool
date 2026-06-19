# RepoLens v0.2 Planning Interview Summary

Date: 2026-06-18
Source plan: `docs/repolens-v0.2-plan.md`

## Codebase Findings

- No root `CONTEXT.md`, no `CONTEXT-MAP.md`, and no `docs/adr/` exist yet.
- v0.1 already has MCP envelopes, missing-graph responses, ambiguity handling, impact and reading-order heuristics, status freshness, schema checks, update change classes, and safety tests.
- v0.1 does not appear to have a repo-wide canonical graph hash or graph validation service.
- Current edge payloads expose `metadata`, but not first-class `confidence`, `evidence`, or `resolution_strategy`.
- Python imports are classified but not resolved to local module files.
- JS/TS has simple TypeScript alias resolution, but relative `./` and `../` imports are still unresolved.

## Decisions Recorded

- v0.2 is a reliability-hardening release over existing v0.1 behavior, not a broad feature-expansion release.
- v0.2 release gate requires P0 hardening, full verification, self-dogfooding, at least one Python repo, one JS/TS repo, and one mixed docs/config repo, with bugs converted to fixtures or documented as known limitations.
- Release blockers are P0 hardening themes plus dogfooding/regression capture, minimal CI/release smoke, and user/assistant docs.
- Tree-sitter remains non-blocking and experimental.
- Canonical graph hash means a repo-wide structural hash excluding timestamps, mtimes, raw/normalized file hashes, absolute paths, and line-only evidence.
- Edge `confidence`, `evidence`, and `resolution_strategy` should become first-class edge contract fields.
- Duplicate logical edges use `(source_id, target_id, kind)` identity and merge evidence/strategies.
- Graph validation failures abort before replacing artifacts and preserve the previous graph.
- v0.2 keeps rebuild-on-incompatibility; no SQLite migration framework yet.
- Python resolver scope is deterministic local resolution only.
- JS/TS resolver scope is relative imports plus simple deterministic aliases, without full TypeScript/package/bundler resolution.
- Low-confidence fuzzy matches are candidates only and must not be stored as graph edges.
- Impact Analysis means graph-derived edit-planning context, not runtime certainty. Its canonical response model is grouped by dependencies, dependents, tests, docs, configs, commands, and risks; rollups are derived convenience fields.
- Impact traversal uses containment only for bounded Target Expansion. It must not traverse upward through containers and sideways into sibling nodes.
- The v0.2 MCP contract standardizes the existing v0.1 envelope shape instead of replacing it with the draft example shape. MCP success responses always include `ok`, `data`, `warnings`, `limits`, `confidence`, `evidence`, `freshness`, and `truncation`; `pagination` appears where applicable and `error` appears on failures.
- The strict shared envelope contract applies to MCP tools. CLI JSON can reuse helpers gradually but is not required to expose MCP-only fields in v0.2.
- Missing or unavailable graph artifacts are structured `ok: false` errors in MCP, including `graph_status`; CLI status may still report missing graph as a successful status result.
- Selective Update is a v0.2 release requirement, not just improved change reporting.
- Selective Update operates at file-level replacement granularity, not symbol-level mutation.
- Selective Update performance is gated by relative speedup against full rebuild on a generated fixture, not an absolute wall-clock budget.
- Large performance fixtures should be generated deterministically, not committed as large fixture trees.
- Redaction Policy uses shared high-risk redaction for obvious secrets across artifacts and output while preserving useful paths, package names, and symbol names.
- Package Boundary detection requires explicit deterministic package/config evidence; directory conventions alone are not enough.
- Dogfooding runs use real local repositories, but committed artifacts should be reports, distilled regression fixtures, and known limitations rather than vendored third-party snapshots.
- Minimal CI is a v0.2 release blocker: Ruff check, Ruff format check, mypy, pytest, package build, and isolated install smoke. Docker smoke, release checklist, changelog, and docs are separate release-prep/docs slices. Publishing automation remains out of scope.
- The v0.2 backlog should be re-sliced into dependency-ordered vertical issues rather than keeping the draft 18 theme-bucket issues unchanged.
- Edge Contract storage uses explicit edge trust/strategy columns plus bounded normalized evidence JSON. Edge-specific metadata remains separate.
- Canonical Graph Hash covers the stable structural graph contract only, excluding volatile run metadata, file-system metadata, absolute paths, export formatting, and line-only movement.
- Graph Validation has hard invariants that block artifact replacement and non-blocking quality warnings for expected incompleteness.
- Resolution Strategy uses a small canonical cross-language vocabulary for successful relationships and candidates, distinct from language-specific unresolved status strings.
- Python import resolution remains deterministic local-only and does not emulate Python runtime import behavior.
- JS/TS relative imports should become indexed graph edges alongside simple deterministic aliases; full TypeScript/package/bundler semantics remain out of scope.
- Deterministic test path/name similarity becomes stored medium-confidence Related Test relationships, with direct imports ranked higher.
- RepoLens should use Candidate Verification Command language and must not imply commands were run or should be automatically executed.
- The MCP/source safety guarantee is No Whole-Source Disclosure: `search_text` may read scanner-approved live text but returns only bounded sanitized previews.
- Parser Backend abstraction and Tree-sitter remain non-blocking P1 experiments unless dogfooding proves parser limitations block P0 reliability.
- README should stay a quickstart and safety overview, with focused docs for MCP examples, assistant usage, security/artifact privacy, troubleshooting, known limitations, and release readiness.
- Issue labels should use a small taxonomy: `v0.2`, `P0/P1/P2`, and area labels such as `area:graph`, `area:resolver`, `area:mcp`, `area:update`, `area:security`, `area:package-workspace`, `area:dogfood`, `area:ci`, and `area:docs`.
- `docs/repolens-v0.2-planning-interview-summary.md` is the decision log. Patch `docs/repolens-v0.2-plan.md` only where it contradicts resolved decisions.

## Resolved Interview Areas

- Impact analysis response model and traversal boundaries.
- MCP envelope exact shape and compatibility with current v0.1 responses.
- Incremental update planner and selective reparse behavior.
- Redaction and security hardening scope.
- Package/workspace awareness boundary.
- Dogfooding target selection.
- CI/release/docs issue slicing.
- Edge contract storage and resolution strategy taxonomy.
- Canonical graph hash and validation severity.
- Source disclosure safety wording.
- Parser abstraction release-blocking boundary.
- Issue labels and decision-log source of truth.

## Issue Implications

- Reword v0.2 issues as hardening and normalization work where v0.1 already has partial behavior.
- Keep parser abstraction and Tree-sitter out of the release-blocking path unless later dogfooding proves they are required.
- Add a graph validation and canonical hash issue before deeper resolver or MCP polish work, because those later features depend on stable facts.
- Add explicit edge contract work before query/API polish, because MCP responses should expose the same edge confidence and evidence model everywhere.
- Split Python local import resolution from JS/TS relative import resolution so each can be fixture-driven and reviewed independently.
