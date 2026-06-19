# RepoLens v0.2 Issue Breakdown Feedback

## Overall verdict

Approve the direction, but revise before publishing GitHub issues.

The v0.2 issue breakdown is strong because it treats v0.2 as a reliability-hardening release rather than a rewrite. It correctly focuses on graph correctness, edge trust, deterministic resolution, impact analysis quality, MCP contract stability, selective update correctness, security, dogfooding, CI, and documentation.

The current breakdown is close to publishable. The main problems are not the theme or scope, but dependency bottlenecks and a few oversized slices.

## What is working well

### 1. The release theme is correct

The strongest v0.2 scope remains:

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

This is the right upgrade path from v0.1. v0.2 should improve trust and usefulness of the existing local-first graph system before adding deeper semantic analysis.

### 2. The issue list is better than the original theme buckets

The current issue breakdown is dependency-ordered and implementation-oriented. That is better than publishing the earlier theme-bucket list directly.

Good examples:

- Edge contract storage comes before resolver and MCP polish.
- Canonical graph hash and validation come before deeper resolution work.
- Python and JS/TS resolver work are split.
- Candidate-only ambiguity handling is explicit.
- Impact analysis and reading order are separate but connected.
- Selective update has both implementation and verification slices.
- Dogfooding is treated as a release-confidence requirement.

### 3. Tree-sitter is correctly non-blocking

Keeping parser abstraction and optional Tree-sitter as P1 is the right call. It can stay in the v0.2 milestone as an experiment, but it should not block the release unless dogfooding proves default parser limitations are blocking P0 reliability.

### 4. The edge contract direction is strong

Making `confidence`, `resolution_strategy`, and bounded normalized `evidence` first-class edge fields is a good foundation. It prevents MCP and query tools from hiding trust/provenance inside generic metadata.

Duplicate logical edge merging by `(source_id, target_id, kind)` is also the right level of normalization for v0.2.

## Main changes to make before publishing

## 1. Move MCP envelope foundation earlier

Current issue:

```text
10. Standardize MCP Response Envelope, errors, pagination, and stdio discipline
Blocked by: 8, 9
```

This should change.

The MCP envelope is a contract foundation. If impact analysis and reading order are implemented before the shared envelope helpers, those tools may create response shapes that later need rework.

Split issue 10 into two issues:

### 10a. Add shared MCP envelope foundation and contract tests

Suggested metadata:

```text
Title: Add shared MCP envelope foundation and contract tests
Type: AFK
Priority: P0
Area labels: area:mcp
Blocked by: 2, maybe 3
```

Scope:

- Shared success envelope helper.
- Shared structured error helper.
- Missing/unavailable graph error shape.
- Stale warning format.
- Truncation metadata.
- Pagination metadata where applicable.
- Response caps helper.
- Stdio discipline test support.
- Contract tests for the envelope itself.

This issue should not wait for impact analysis or reading order.

### 10b. Migrate MCP tools to standardized envelope, errors, pagination, and stdio discipline

Suggested metadata:

```text
Title: Migrate MCP tools to standardized envelope, errors, pagination, and stdio discipline
Type: AFK
Priority: P0
Area labels: area:mcp
Blocked by: 8, 9, 10a
```

Scope:

- Migrate all MCP tools to the shared envelope helper.
- Ensure expected failures use structured errors.
- Ensure tools work before indexing with actionable missing-graph responses.
- Ensure large responses are capped/paginated/truncated consistently.
- Ensure no stdout logging in stdio mode.

## 2. Do not let a P1 issue block P0 dogfooding

Current issue 16 is blocked by issue 14:

```text
16. Add Dogfooding Reports and regression fixture process
Blocked by: 10, 12, 13, 14
```

But issue 14 is P1:

```text
14. Improve Package Boundary, workspace, and command grouping awareness
Priority: P1
```

This creates a hidden release blocker: a P1 issue blocks a P0 dogfooding issue.

Choose one of these options:

### Preferred option

Keep issue 14 as P1 and remove it from issue 16's blockers.

Dogfooding should validate the P0 system first. If package/workspace awareness causes real dogfooding problems, convert those findings into P0 bugs or known limitations.

### Alternative option

Promote issue 14 to P0 if package/workspace awareness is mandatory for v0.2 release quality.

I do not recommend this unless dogfooding proves it is necessary.

## 3. Split CI from docs and release readiness

Current issue 17 is too large:

```text
17. Add minimal CI, release readiness docs, and v0.2 user docs
```

It combines:

- Ruff check.
- Ruff format check.
- Mypy.
- Pytest.
- Package build.
- Isolated install smoke.
- README updates.
- MCP examples.
- Assistant usage guide.
- Security/artifact privacy docs.
- Troubleshooting guide.
- Known limitations.
- Release checklist.
- Changelog template.

Split this into two issues.

### 17. Add minimal CI and isolated install smoke

Suggested metadata:

```text
Title: Add minimal CI and isolated install smoke
Type: AFK
Priority: P0
Area labels: area:ci
Blocked by: enough tests existing; does not need docs
```

Scope:

- GitHub Actions workflow.
- Ruff check.
- Ruff format check.
- Mypy.
- Pytest.
- Package build.
- Isolated install smoke.
- `repolens --help` smoke.
- One fixture index smoke if practical.

### 18. Add v0.2 user docs, assistant docs, release checklist, and known limitations

Suggested metadata:

```text
Title: Add v0.2 user docs, assistant docs, release checklist, and known limitations
Type: AFK with HITL checkpoint
Priority: P0
Area labels: area:docs
Blocked by: dogfooding report and final MCP contract
```

Scope:

- README quickstart and safety overview.
- MCP tool examples.
- Assistant usage guide.
- OpenCode example update.
- Security/artifact privacy documentation.
- Troubleshooting guide.
- Known limitations page.
- Release checklist.
- Changelog template.

## 4. Split security policy from MCP source-disclosure proof

Current issue 13 is useful, but slightly too broad:

```text
13. Add shared Redaction Policy and No Whole-Source Disclosure tests
Blocked by: 10
```

The security policy work does not need to wait for MCP envelope migration. Only the MCP source-disclosure proof depends on MCP response shapes.

Split it into two issues.

### 13a. Add shared Redaction Policy and scanner/security fixtures

Suggested metadata:

```text
Title: Add shared Redaction Policy and scanner/security fixtures
Type: AFK
Priority: P0
Area labels: area:security
Blocked by: 2 or 3
```

Scope:

- Central redaction utility.
- Secret-like metadata redaction.
- Command string redaction.
- Path containment tests.
- Secret-path skip fixtures.
- Scanner security fixtures.
- Preservation of useful paths, package names, and symbol names.

### 13b. Add MCP No Whole-Source Disclosure and raw text safety tests

Suggested metadata:

```text
Title: Add MCP No Whole-Source Disclosure and raw text safety tests
Type: AFK
Priority: P0
Area labels: area:security, area:mcp
Blocked by: 10a, 13a
```

Scope:

- Raw text search capped sanitized previews only.
- No whole source mirroring through MCP.
- No source-file read tool behavior.
- Search result limits and truncation proof.
- Sanitization tests for source-adjacent outputs.

## Review question answers

## 1. Does the granularity feel right?

Mostly yes.

The current list is already much better than theme-bucket issues. I would only split the overloaded contract/security/release-readiness items.

Recommended splits:

- Split issue 10 into MCP envelope foundation and MCP tool migration.
- Split issue 13 into security policy and MCP no-source-disclosure proof.
- Split issue 17 into minimal CI and docs/release readiness.

This increases issue count, but each issue becomes easier for an AFK agent to implement and verify.

## 2. Are the dependency relationships correct?

Mostly, but change these:

```text
#10a MCP envelope foundation
Blocked by: #2, maybe #3
Not blocked by: #8 or #9

#10b MCP tool migration
Blocked by: #8, #9, #10a

#13a Redaction/security core
Blocked by: #2 or #3

#13b MCP no-source-disclosure tests
Blocked by: #10a, #13a

#16 Dogfooding
Blocked by: #10b, #12, #13b
Do not block on #14 unless #14 becomes P0.

#17 Minimal CI
Blocked by: enough tests existing
Does not need final docs.

#18 Docs/release readiness
Blocked by: #16, #17, final MCP contract
```

## 3. Are the HITL/AFK markings correct?

Mostly yes.

Recommended markings:

```text
#1 Roadmap and release criteria
Type: Tracking / HITL

#2-#15 Core implementation slices
Type: AFK

#16 Dogfooding reports and regression fixture process
Type: HITL

#17 Minimal CI and isolated install smoke
Type: AFK

#18 Docs, release checklist, and known limitations
Type: AFK with HITL checkpoint
```

Dogfooding should stay HITL because real repository selection, false-positive judgment, and known-limitation decisions require human review.

Docs should have a HITL checkpoint because they define user-facing promises.

## 4. Should the optional Parser Backend issue remain in v0.2?

Yes, keep it in the v0.2 milestone as P1.

Do not make it release-blocking.

The issue should clearly state:

- Default parser behavior must remain stable.
- Tree-sitter must be optional.
- The backend must be explicit, for example `--parser-backend default|treesitter`.
- Failures must be nonfatal and clearly reported.
- The issue can be deferred if P0 reliability work runs long.

## 5. Should CI and docs remain combined?

No.

CI is mechanical and should be implemented earlier. Docs should absorb dogfooding findings and final MCP contracts.

Split them.

## Recommended final issue list

```text
1. RepoLens MCP v0.2 roadmap and release criteria
2. Add Edge Contract storage and duplicate edge normalization
3. Add Canonical Graph Hash, Graph Validation, and rebuild guardrails
4. Resolve Python local imports deterministically
5. Resolve JS/TS relative imports and harden simple aliases
6. Normalize Resolution Strategy and candidate-only ambiguity handling
7. Store Related Test relationships with confidence and evidence
8. Group Impact Analysis and enforce Target Expansion traversal boundaries
9. Improve Suggested Reading Order ranking and command context
10. Add shared MCP envelope foundation and contract tests
11. Migrate MCP tools to standardized envelope, errors, pagination, and stdio discipline
12. Add file-level Selective Update planner and graph replacement path
13. Add Selective Update cleanup tests and generated benchmark fixture
14. Add shared Redaction Policy and scanner/security fixtures
15. Add MCP No Whole-Source Disclosure and raw text safety tests
16. Improve Package Boundary, workspace, and command grouping awareness
17. Add optional Parser Backend experiment behind default-stable behavior
18. Add Dogfooding Reports and regression fixture process
19. Add minimal CI and isolated install smoke
20. Add v0.2 user docs, assistant docs, release checklist, and known limitations
```

## Suggested dependency graph

```text
1
└── 2 Edge Contract
    ├── 3 Canonical Hash + Validation
    │   ├── 4 Python Resolver
    │   ├── 5 JS/TS Resolver
    │   ├── 12 Selective Update Planner
    │   └── 17 Parser Backend Experiment
    │
    ├── 10 MCP Envelope Foundation
    │   ├── 11 MCP Tool Migration
    │   │   ├── 15 MCP No Whole-Source Disclosure
    │   │   └── 18 Dogfooding
    │   └── 15 MCP No Whole-Source Disclosure
    │
    ├── 14 Redaction/Security Core
    │   └── 15 MCP No Whole-Source Disclosure
    │
    └── 16 Package/Workspace Awareness

4 + 5
└── 6 Resolution Strategy + Ambiguity
    └── 7 Related Tests
        └── 8 Impact Analysis
            └── 9 Reading Order
                └── 11 MCP Tool Migration

12
└── 13 Selective Update Tests + Benchmark
    └── 18 Dogfooding

18 Dogfooding
├── 19 Minimal CI
└── 20 Docs + Release Readiness
```

## Release-blocking scope

Recommended P0 release blockers:

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

Recommended non-blocking P1:

```text
16. Package/workspace/command grouping awareness
17. Optional Parser Backend experiment
```

Promote #16 only if dogfooding proves package/workspace gaps are release-blocking.

## Final recommendation

Do not publish the current issue breakdown unchanged.

Publish after these edits:

1. Move MCP envelope foundation earlier.
2. Split MCP foundation from MCP tool migration.
3. Split security policy from MCP source-disclosure proof.
4. Remove the P1 package/workspace blocker from dogfooding, or promote it to P0.
5. Split CI from docs/release readiness.
6. Keep Tree-sitter/parser backend as non-blocking P1.

After those changes, the issue breakdown is strong enough to become the v0.2 GitHub backlog.
