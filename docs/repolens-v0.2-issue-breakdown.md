# RepoLens MCP v0.2 Issue Breakdown Archive

Status: archived historical issue breakdown. Published as GitHub issues `#35` through `#54`.

## Source Documents

- `docs/repolens-v0.2-plan.md`
- `docs/repolens-v0.2-planning-interview-summary.md`
- `docs/repolens-v0.2-issue-breakdown-feedback.md`
- `docs/repolens-v0.2-release-tracker.md`
- `CONTEXT.md`
- `docs/adr/0001-standardize-mcp-envelope.md`
- `docs/adr/0002-edge-contract-storage.md`

## Theme

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

## Published Tracker

- Umbrella tracker: `#35` RepoLens MCP v0.2 roadmap and release criteria
- Local tracker: `docs/repolens-v0.2-release-tracker.md`

## Published Slices

| Issue | Priority | Area | Summary |
|---|---|---|---|
| #35 | P0 | docs | Roadmap and release criteria. |
| #36 | P0 | graph | Edge Contract storage and duplicate edge normalization. |
| #37 | P0 | graph | Canonical Graph Hash, Graph Validation, and rebuild guardrails. |
| #38 | P0 | resolver | Deterministic Python local import resolution. |
| #39 | P0 | resolver | JS/TS relative imports and simple aliases. |
| #40 | P0 | resolver, mcp | Resolution Strategy and candidate-only ambiguity handling. |
| #41 | P0 | resolver, graph | Related Test relationships with confidence and evidence. |
| #42 | P0 | mcp, graph | Grouped Impact Analysis and traversal boundaries. |
| #43 | P0 | mcp | Suggested Reading Order ranking and command context. |
| #44 | P0 | mcp | Shared MCP envelope foundation and contract tests. |
| #45 | P0 | mcp | MCP tool migration to envelope, errors, pagination, and stdio discipline. |
| #46 | P0 | update, graph | File-level Selective Update planner and graph replacement. |
| #47 | P0 | update | Selective Update cleanup tests and generated benchmark fixture. |
| #48 | P0 | security | Redaction Policy and scanner/security fixtures. |
| #49 | P0 | security, mcp | MCP No Whole-Source Disclosure and raw text safety tests. |
| #50 | P1 | package-workspace | Package Boundary, workspace, and command grouping awareness. |
| #51 | P1 | graph | Optional Parser Backend experiment behind default-stable behavior. |
| #52 | P0 | dogfood | Dogfooding reports and regression fixture process. |
| #53 | P0 | ci | Minimal CI and isolated install smoke. |
| #54 | P0 | docs | v0.2 user docs, assistant docs, release checklist, and known limitations. |

## Dependency Notes

- Edge Contract storage unlocked graph validation, resolver work, MCP envelope work, redaction, and optional package/parser work.
- Canonical Graph Hash and validation unlocked resolver and selective update work.
- MCP envelope foundation intentionally started before full MCP tool migration.
- Dogfooding depended on MCP migration, selective update tests, and source-disclosure safety, but not P1 package/workspace work.
- Docs and release readiness depended on dogfooding, minimal CI, and final MCP contract behavior.

## Release-Blocking Scope

All P0 items except P1 package/workspace awareness and optional parser backend were release blockers.

P1 work stayed non-blocking unless dogfooding promoted a concrete gap to P0.
