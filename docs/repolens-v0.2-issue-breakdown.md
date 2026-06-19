# RepoLens MCP v0.2 Issue Breakdown

Draft status: Final review complete. Approved to become GitHub issue bodies.

Source documents:

- `docs/repolens-v0.2-plan.md`
- `docs/repolens-v0.2-planning-interview-summary.md`
- `docs/repolens-v0.2-issue-breakdown-feedback.md`
- `CONTEXT.md`
- `docs/adr/0001-standardize-mcp-envelope.md`
- `docs/adr/0002-edge-contract-storage.md`

Release theme:

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

Label taxonomy:

- Version: `v0.2`
- Priority: `P0`, `P1`, `P2`
- Areas: `area:graph`, `area:resolver`, `area:mcp`, `area:update`, `area:security`, `area:package-workspace`, `area:dogfood`, `area:ci`, `area:docs`

## Proposed Slices

1. Title: RepoLens MCP v0.2 roadmap and release criteria
   Type: Tracking / HITL
   Priority: P0
   Area labels: `area:docs`
   Blocked by: None
   User stories covered: v0.2 coordination and release acceptance
   Notes: Umbrella tracker for release scope, labels, blockers, dogfooding targets, and known limitations.

2. Title: Add Edge Contract storage and duplicate edge normalization
   Type: AFK
   Priority: P0
   Area labels: `area:graph`
   Blocked by: 1
   User stories covered: graph trust, MCP evidence consistency, resolver explainability
   Notes: Adds first-class edge confidence, resolution strategy, bounded evidence JSON, duplicate logical edge merge by `(source_id, target_id, kind)`, deterministic evidence ordering, and schema version bump. Follows ADR 0002.

3. Title: Add Canonical Graph Hash, Graph Validation, and rebuild guardrails
   Type: AFK
   Priority: P0
   Area labels: `area:graph`
   Blocked by: 2
   User stories covered: deterministic graph facts, safe artifact replacement, schema stability
   Notes: Adds structural canonical hash, hard graph invariants, non-blocking quality warnings, validation-before-replace behavior, unsupported schema/config/parser rebuild handling, and regression tests for stable IDs and whitespace-only edits.

4. Title: Resolve Python local imports deterministically
   Type: AFK
   Priority: P0
   Area labels: `area:resolver`
   Blocked by: 3
   User stories covered: Python reference resolution, dependency impact, local package roots
   Notes: Resolves scanner-approved local Python modules from absolute and relative imports using deterministic local roots and module maps. Leaves runtime import behavior, namespace/package environment behavior, and ambiguous targets unresolved or candidate-only.

5. Title: Resolve JS/TS relative imports and harden simple aliases
   Type: AFK
   Priority: P0
   Area labels: `area:resolver`
   Blocked by: 3
   User stories covered: JS/TS reference resolution, deterministic aliases, import impact
   Notes: Stores relative `./` and `../` imports as graph edges, preserves simple TypeScript alias support, adds evidence and resolution strategies, and keeps TypeScript compiler/package/bundler semantics out of scope.

6. Title: Normalize Resolution Strategy and candidate-only ambiguity handling
   Type: AFK
   Priority: P0
   Area labels: `area:resolver`, `area:mcp`
   Blocked by: 4, 5
   User stories covered: explainable resolution, ambiguous reference safety, fuzzy candidates
   Notes: Introduces the canonical strategy vocabulary across query and MCP output. Keeps low-confidence fuzzy matches as candidates only and prevents candidate-only matches from becoming graph edges.

7. Title: Store Related Test relationships with confidence and evidence
   Type: AFK
   Priority: P0
   Area labels: `area:resolver`, `area:graph`
   Blocked by: 6
   User stories covered: related tests, impact confidence, reading order quality
   Notes: Stores direct-import test relationships as high confidence and deterministic path/name similarity as medium confidence. Ensures test relationships never imply coverage certainty.

8. Title: Group Impact Analysis and enforce Target Expansion traversal boundaries
   Type: AFK
   Priority: P0
   Area labels: `area:mcp`, `area:graph`
   Blocked by: 7
   User stories covered: impact analysis, edit-planning context, traversal safety
   Notes: Makes grouped impact categories primary, keeps rollups derived, uses Target Expansion without upward/sibling containment traversal, includes reasons/confidence/evidence, and avoids runtime-certainty language.

9. Title: Improve Suggested Reading Order ranking and command context
   Type: AFK
   Priority: P0
   Area labels: `area:mcp`
   Blocked by: 8
   User stories covered: reading order, related tests, candidate verification commands
   Notes: Adds ranking reasons, task-token matching improvements, likely test inclusion, contextual docs/configs, and Candidate Verification Command output that is sanitized, marked not run, and not auto-run-recommended.

10. Title: Add shared MCP envelope foundation and contract tests
    Type: AFK
    Priority: P0
    Area labels: `area:mcp`
    Blocked by: 2
    User stories covered: MCP contract foundation, structured errors, bounded response metadata
    Notes: Adds shared success and structured error helpers, missing/unavailable graph error shape, stale warning format, truncation metadata, pagination metadata where applicable, response cap helpers, stdio discipline test support, and envelope contract tests. Follows ADR 0001 and does not wait for impact analysis or reading order.

11. Title: Migrate MCP tools to standardized envelope, errors, pagination, and stdio discipline
    Type: AFK
    Priority: P0
    Area labels: `area:mcp`
    Blocked by: 8, 9, 10
    User stories covered: MCP contract reliability, missing graph recovery, bounded responses
    Notes: Migrates all MCP tools to the shared envelope helper, ensures expected failures use structured errors, verifies tools work before indexing with actionable missing-graph responses, caps/paginates/truncates large responses consistently, and preserves no-stdout logging in stdio mode.

12. Title: Add file-level Selective Update planner and graph replacement path
    Type: AFK
    Priority: P0
    Area labels: `area:update`, `area:graph`
    Blocked by: 3, 4, 5
    User stories covered: update correctness, reuse unchanged facts, file-level reparse
    Notes: Plans changed/new/deleted/skipped/parse-error files, reuses unchanged facts, reparses changed files, removes stale facts for deleted/unparseable files, recomputes affected cross-file edges, and falls back to full rebuild when safety checks require it.

13. Title: Add Selective Update cleanup tests and generated benchmark fixture
    Type: AFK
    Priority: P0
    Area labels: `area:update`
    Blocked by: 12
    User stories covered: stale fact cleanup, parse-error cleanup, update performance evidence
    Notes: Adds deleted-file cleanup, parse-error cleanup, config/parser invalidation cases, generated large fixture tooling, and relative speedup evidence against full rebuild without hard wall-clock promises.

14. Title: Add shared Redaction Policy and scanner/security fixtures
    Type: AFK
    Priority: P0
    Area labels: `area:security`
    Blocked by: 3
    User stories covered: artifact privacy, command/config redaction, scanner safety, path containment
    Notes: Adds a central redaction utility, secret-like metadata redaction, command string redaction, path containment tests, secret-path skip fixtures, scanner security fixtures, and regression coverage that preserves useful paths, package names, and symbol names.

15. Title: Add MCP No Whole-Source Disclosure and raw text safety tests
    Type: AFK
    Priority: P0
    Area labels: `area:security`, `area:mcp`
    Blocked by: 10, 14
    User stories covered: source-disclosure safety, raw text search safety, MCP response bounds
    Notes: Proves raw text search returns capped sanitized previews only, no MCP tool mirrors complete source files, no source-file read tool behavior exists, search result limits/truncation are explicit, and source-adjacent outputs are sanitized.

16. Title: Improve Package Boundary, workspace, and command grouping awareness
    Type: AFK
    Priority: P1
    Area labels: `area:package-workspace`
    Blocked by: 2, 14
    User stories covered: monorepos, package roots, commands by package/config root
    Notes: Adds explicit-evidence package/workspace boundaries, command grouping by nearest defining config/package root, package manager detection improvements, and shallow safe config normalization. Directory conventions alone are not package evidence. This is non-blocking for v0.2 unless dogfooding promotes it to P0.

17. Title: Add optional Parser Backend experiment behind default-stable behavior
    Type: AFK
    Priority: P1
    Area labels: `area:graph`
    Blocked by: 3
    User stories covered: parser extensibility, optional Tree-sitter comparison
    Notes: Adds a parser backend interface and optional experiment only if it does not destabilize default parser behavior. Tree-sitter remains optional, explicit, nonfatal on failure, and non-blocking for v0.2 release.

18. Title: Add Dogfooding Reports and regression fixture process
    Type: HITL
    Priority: P0
    Area labels: `area:dogfood`
    Blocked by: 11, 13, 15
    User stories covered: real-world validation, false-positive/false-negative tracking, release confidence
    Notes: Dogfoods RepoLens on itself plus local Python, JS/TS, and mixed docs/config repositories. Commits reports, known limitations, and distilled regression fixtures, not vendored third-party snapshots. Does not block on P1 package/workspace work; dogfooding findings can promote package/workspace gaps to P0 bugs or known limitations. v0.2 release still requires issue 19 minimal CI to pass.

19. Title: Add minimal CI and isolated install smoke
    Type: AFK
    Priority: P0
    Area labels: `area:ci`
    Blocked by: 1
    User stories covered: automated release gate, build/install confidence
    Notes: Starts early after roadmap/labels exist. Adds GitHub Actions for Ruff check, Ruff format check, mypy, pytest, package build, isolated install smoke, `repolens --help` smoke, and one fixture index smoke once fixture coverage is stable. Does not need final docs.

20. Title: Add v0.2 user docs, assistant docs, release checklist, and known limitations
    Type: AFK with HITL checkpoint
    Priority: P0
    Area labels: `area:docs`
    Blocked by: 11, 18, 19
    User stories covered: user onboarding, assistant usage, release readiness, known limitations
    Notes: Updates README as quickstart/safety overview and adds focused MCP tool examples, assistant usage guide, OpenCode example update, security/artifact privacy documentation, troubleshooting guide, known limitations page, release checklist, and changelog template. Publishing automation remains out of scope.

## Suggested Dependency Graph

```text
1 Roadmap
`-- 2 Edge Contract
    |-- 3 Canonical Hash + Validation
    |   |-- 4 Python Resolver
    |   |-- 5 JS/TS Resolver
    |   |-- 12 Selective Update Planner
    |   |-- 14 Redaction/Security Core
    |   `-- 17 Parser Backend Experiment (P1)
    |
    |-- 10 MCP Envelope Foundation
    |   |-- 11 MCP Tool Migration
    |   `-- 15 MCP No Whole-Source Disclosure
    |
    `-- 16 Package/Workspace Awareness (P1)

4 + 5
`-- 6 Resolution Strategy + Ambiguity
    `-- 7 Related Tests
        `-- 8 Impact Analysis
            `-- 9 Reading Order
                `-- 11 MCP Tool Migration

12
`-- 13 Selective Update Tests + Benchmark
    `-- 18 Dogfooding

14 Redaction/Security Core
`-- 15 MCP No Whole-Source Disclosure
    `-- 18 Dogfooding

18 Dogfooding
`-- 20 Docs + Release Readiness

19 Minimal CI
`-- 20 Docs + Release Readiness
```

## Release-Blocking Scope

P0 release blockers:

```text
1. Roadmap/release criteria
2. Edge Contract storage
3. Canonical Graph Hash + Validation
4. Python local import resolution
5. JS/TS relative import resolution
6. Resolution Strategy + ambiguity handling
7. Related Test relationships
8. Impact Analysis grouping/traversal safety
9. Reading Order ranking/reasons
10. MCP envelope foundation
11. MCP tool migration
12. Selective Update planner
13. Selective Update cleanup/benchmark tests
14. Redaction/security core
15. MCP no-source-disclosure tests
18. Dogfooding reports/regression fixture process
19. Minimal CI/install smoke
20. Docs/release readiness
```

Non-blocking P1:

```text
16. Package/workspace/command grouping awareness
17. Optional Parser Backend experiment
```

Promote issue 16 only if dogfooding proves package/workspace gaps are release-blocking.

## Review Decisions

1. This revised split is ready to become GitHub issue bodies.
2. Issue 19, minimal CI, may start immediately after enough tests exist; it does not need to block on a specific core issue.
3. Issue 16 stays in the v0.2 milestone as P1 unless dogfooding promotes it to P0.
