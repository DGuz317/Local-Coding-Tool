# RepoLens MCP v0.2 Plan

Version: Draft 1 
Date: 2026-06-18 
Scope: Upgrade path from RepoLens MCP v0.1 to v0.2

## 1. Positioning

RepoLens v0.2 should make v0.1 reliable on real repositories before moving into deep semantic analysis. The release should improve graph correctness, reference resolution, impact analysis, MCP query quality, update performance, and security hardening while keeping the product deterministic, local-first, read-only through MCP, and safe by default.

v0.2 should not be a rewrite. It should preserve the v0.1 contract: local `.repolens` artifacts, SQLite as the authoritative graph store, deterministic exports, read-only MCP tools, no required AI model, no required embeddings, and no runtime network dependency for normal indexing or serving.

## 2. Goals

- Improve trust in graph facts through stronger evidence, confidence, validation, and schema stability.
- Improve reference resolution for Python, JS, TS, docs, configs, packages, tests, and entrypoints.
- Make impact analysis and suggested reading order more useful before editing.
- Polish MCP responses so agents can consume RepoLens results predictably.
- Make update/status behavior faster and more accurate on real repos.
- Harden privacy and safety behavior around paths, secrets, command strings, raw search, and artifacts.
- Introduce parser abstraction so optional Tree-sitter support can be tested without replacing v0.1 parsers.
- Add enough CI/release automation to make repeated releases safe.

## 3. Non-goals

- No cloud dashboard.
- No hosted sync.
- No telemetry.
- No write-capable MCP tools.
- No automatic code editing.
- No PR review bot behavior.
- No required embeddings or vector database.
- No Kuzu migration in v0.2.
- No full CFG, reaching definitions, taint analysis, or deep semantic call graph.
- No full TypeScript compiler resolution.
- No full framework route extraction.
- No browser UI.

## 4. Theme summary

| Priority | Theme | Main outcome |
|---|---|---|
| P0 | Graph correctness and schema stability | Graph facts are more stable, validated, and explainable. |
| P0 | Better reference resolution | More imports, packages, paths, tests, and symbols resolve deterministically. |
| P0 | Richer impact analysis and reading-order quality | Assistants get better pre-edit context with evidence and reasons. |
| P0 | MCP contract polish and query UX | MCP tools return consistent, capped, paginated, evidence-backed responses. |
| P0 | Incremental update correctness and performance | `update` and `status` become faster and more accurate. |
| P0 | Security/privacy hardening | Artifacts and MCP output are safer for real repositories. |
| P1 | Parser abstraction and optional Tree-sitter backend | Tree-sitter can be tested behind an optional backend without becoming required. |
| P1 | Better package/workspace/config awareness | Monorepos and multi-package projects are represented more clearly. |
| P1 | Real-world dogfooding and fixture expansion | Bugs from real repos become permanent fixtures and regression tests. |
| P2 | CI/release automation | Build, install, Docker, and MCP smoke checks are repeatable. |
| P2 | Documentation and assistant-usage examples | Users and agents know how to use v0.2 features safely. |

## 5. Theme details

### 5.1 Graph correctness and schema stability

Problem: v0.1 creates a useful graph, but v0.2 needs stronger guarantees that graph facts are stable, deterministic, and explainable across updates.

Deliverables:

- Graph validation service.
- Schema compatibility check.
- Stable node ID audit.
- Duplicate edge merge audit.
- Evidence normalization.
- Edge confidence calibration.
- Graph diff report for `update`.
- Rebuild trigger when schema/parser/config versions are incompatible.

Acceptance criteria:

- Running `index` twice on the same repo produces the same canonical graph hash.
- Whitespace-only edits do not create structural graph changes unless symbol boundaries actually change.
- Duplicate logical edges are merged with aggregated evidence.
- Every edge exposed through MCP has confidence and evidence.
- Unsupported schema versions trigger a clear rebuild path.
- Graph validation failures are reported without corrupting the existing graph.

Suggested issues:

- Add graph validation service.
- Add graph diff report for update summaries.
- Add schema compatibility and rebuild policy.
- Add stable node ID regression tests.

### 5.2 Better reference resolution

Problem: v0.1 should be conservative. v0.2 should resolve more references while still avoiding unsupported guesses.

Deliverables:

- Deterministic Python import root inference improvements.
- Python relative import resolution.
- JS/TS relative import resolution improvements.
- Deterministic TypeScript path alias resolution.
- Import alias handling.
- Package root resolution.
- Test relationship resolution by direct imports and path/name similarity.
- Candidate-only fuzzy search for ambiguous references.
- Resolution strategy metadata stored with edges.

Resolution policy:

- High confidence: same-file symbol, explicit local import, exact path mention, declared command, declared package.
- Medium confidence: source-root inference, deterministic path alias, test path/name similarity.
- Low confidence: fuzzy candidate only; do not silently resolve.

Acceptance criteria:

- Ambiguous references return candidates instead of choosing silently.
- Resolved edges include strategy, confidence, and evidence.
- Python import fixtures cover package roots, relative imports, aliases, and syntax errors.
- JS/TS fixtures cover relative imports, exports, CommonJS, package roots, and deterministic aliases.
- Resolution can be rerun without reparsing unchanged files.

Suggested issues:

- Improve Python import resolver.
- Improve JS/TS import resolver.
- Add deterministic TypeScript alias support.
- Add resolution strategy metadata.
- Add candidate-only fuzzy matching.

### 5.3 Richer impact analysis and reading-order quality

Problem: v0.1 impact analysis can be shallow. v0.2 should make it useful enough for assistants to plan edits before opening source files.

Deliverables:

- Impact result grouping: dependencies, dependents, tests, docs, configs, commands, risks.
- Container-aware expansion for file/class/module targets.
- Contains-edge exclusion to prevent sibling explosion.
- Reading-order ranking reasons.
- Test relationship confidence.
- Candidate verification commands marked as not run.
- Task-token matching for reading order.

Acceptance criteria:

- Impact analysis never claims runtime certainty.
- Impact results include reasons and confidence.
- Class/module impact does not explode through parent containment edges.
- Reading order defaults to a small useful file set.
- Reading order includes likely tests when task-relevant.
- Verification commands are clearly marked as candidates and not run.

Suggested issues:

- Add grouped impact response model.
- Add container-aware impact traversal.
- Add reading-order ranking reasons.
- Add related-test scoring improvements.
- Add command recommendation safety labels.

### 5.4 MCP contract polish and query UX

Problem: MCP is the main assistant interface. v0.2 should make results consistent, bounded, easy to trust, and easy to recover from when missing or stale.

Deliverables:

- Shared MCP response envelope.
- Structured error payloads.
- Consistent pagination and truncation metadata.
- Consistent stale warnings.
- Better tool descriptions.
- Ambiguity response format.
- Missing-graph response format.
- Response-size caps per tool.
- No stdout logging in stdio mode.

MCP response envelope:

```json
{
  "ok": true,
  "data": {},
  "warnings": [],
  "limits": [],
  "confidence": "high",
  "evidence": [],
  "freshness": {},
  "truncation": {"fields": [], "truncated": false},
  "pagination": {}
}
```

Acceptance criteria:

- Every MCP success response uses the standardized v0.1-compatible envelope.
- Every expected MCP error uses a structured error payload.
- Tools work before indexing and return actionable missing-graph responses.
- Tools never expose whole source files; raw text search returns only scanner-approved capped sanitized previews.
- Tools never execute commands.
- Tools do not write logs/progress to stdout in stdio mode.

Suggested issues:

- Add shared MCP envelope.
- Normalize MCP error handling.
- Add pagination/truncation metadata.
- Improve MCP tool descriptions for assistants.
- Add stdio discipline tests.

### 5.5 Incremental update correctness and performance

Problem: v0.2 should make repeated indexing after edits fast and trustworthy.

Deliverables:

- Update planner that classifies changed, new, deleted, skipped, and parse-error files.
- Selective reparse based on raw hash, normalized hash, graph hash, parser version, and config hash.
- Deleted-file cleanup verification.
- Parse-error stale-fact cleanup.
- Large-repo benchmark fixtures.
- Optional deterministic `--jobs` design, even if not enabled by default.
- Status TTL cache for MCP freshness checks.

Acceptance criteria:

- Deleted files remove stale graph facts.
- Parser errors remove stale graph facts for that file and are nonfatal.
- Config/parser version changes force appropriate reparsing.
- `status` remains read-like and does not mutate artifacts.
- `update` reports primary and secondary change signals.
- Large fixture updates are measurably faster than full rebuilds.

Suggested issues:

- Add update planner.
- Add deleted-file cleanup tests.
- Add parse-error cleanup tests.
- Add graph hash stability tests.
- Add large-repo benchmark fixture.

### 5.6 Security/privacy hardening

Problem: RepoLens artifacts and MCP output can expose repository metadata. v0.2 should harden redaction, containment, and safe output behavior.

Deliverables:

- Redaction utility for secret-like metadata and commands.
- Expanded secret-path skip tests.
- Path containment fuzz tests.
- Raw text search sanitization tests.
- Safe command labeling.
- Artifact privacy documentation.
- Agent instruction file handling rules.
- MCP no-source-read guarantee tests.

Acceptance criteria:

- Secret-looking files are skipped before parsing.
- Secret-like command strings are sanitized before storage/output.
- Absolute paths are normalized to repo-relative paths when inside root.
- Path traversal inputs are rejected.
- Raw text search returns capped sanitized previews only.
- Deploy/publish-like commands are not recommended for automatic execution.

Suggested issues:

- Add redaction utility.
- Add scanner security fixture suite.
- Add raw text search safety tests.
- Add MCP no-source-read tests.
- Document artifact privacy behavior.

### 5.7 Parser abstraction and optional Tree-sitter backend

Problem: v0.1 defers Tree-sitter. v0.2 can introduce parser abstraction and an optional Tree-sitter backend without making it mandatory.

Deliverables:

- Parser backend interface.
- Parser capability model.
- Output comparison harness between default parsers and Tree-sitter.
- Optional install extra, for example `repolens[treesitter]`.
- CLI flag, for example `--parser-backend default|treesitter`.
- Fallback behavior when Tree-sitter is unavailable or fails.

Acceptance criteria:

- Default install still works without Tree-sitter.
- Default parser behavior remains stable.
- Tree-sitter backend can be enabled explicitly.
- Tree-sitter failures are nonfatal and clearly reported.
- Comparison tests show where Tree-sitter improves or differs from default parsing.

Suggested issues:

- Add parser backend interface.
- Add parser capability metadata.
- Add optional Tree-sitter Python backend experiment.
- Add Tree-sitter comparison fixtures.

### 5.8 Better package/workspace/config awareness

Problem: Real repositories often have multiple package roots, task files, Docker files, CI workflows, and mixed language areas. v0.2 should improve these signals.

Deliverables:

- Better Python package root detection.
- Better JS/TS package root detection.
- Monorepo root/package boundary detection.
- Command grouping by package/config root.
- Package manager detection improvements.
- Workspace metadata nodes where deterministic.
- Improved config fact normalization.

Acceptance criteria:

- Commands are grouped by the package or config root that defines them.
- Monorepo package roots appear as graph nodes.
- External packages distinguish declared dependencies from observed imports.
- Python stdlib and Node built-ins remain separated from third-party packages.
- Arbitrary JSON/YAML/TOML remains shallow and safe.

Suggested issues:

- Improve package root detection.
- Add workspace/package nodes.
- Improve command grouping.
- Improve package manager detection.
- Add config normalization tests.

### 5.9 Real-world dogfooding and fixture expansion

Problem: v0.2 should be shaped by real repositories, not only synthetic fixtures.

Deliverables:

- Dogfood RepoLens on itself.
- Dogfood on representative Python repos.
- Dogfood on representative JS/TS repos.
- Dogfood on mixed docs/config repos.
- Convert bugs into fixtures.
- Track false positives and false negatives.
- Track index/update time.

Acceptance criteria:

- Every dogfooding bug has a regression fixture or documented deferral.
- At least one Python, one JS/TS, and one mixed docs/config fixture are included.
- Dogfooding report lists graph quality issues, resolver misses, performance problems, and UX friction.
- v0.2 release notes include known limitations.

Suggested issues:

- Create dogfooding checklist.
- Add RepoLens self-dogfood report.
- Add mixed fixture repository suite.
- Add false-positive/false-negative tracker.

### 5.10 CI/release automation

Problem: v0.2 should be easier to release repeatedly and safely.

Deliverables:

- GitHub Actions for lint, format check, typecheck, tests, and build.
- Isolated install smoke test.
- Docker build smoke test.
- Optional Docker MCP smoke test.
- Release checklist.
- Changelog template.
- Version bump process.

Acceptance criteria:

- CI runs Ruff check, Ruff format check, mypy, pytest, and package build.
- Docker build smoke succeeds in release-prep path.
- Native install smoke can run `repolens --help` and one fixture index.
- Release checklist is documented.

Suggested issues:

- Add CI workflow.
- Add package build verification.
- Add isolated install smoke.
- Add Docker smoke.
- Add release checklist and changelog template.

### 5.11 Documentation and assistant-usage examples

Problem: v0.2 features should be usable by both humans and agents.

Deliverables:

- v0.2 README updates.
- MCP tool guide.
- Assistant prompt guidance.
- OpenCode example update.
- Security/artifact privacy page.
- Troubleshooting page.
- Known limitations page.

Acceptance criteria:

- README explains native install, Docker usage, indexing, updating, MCP configuration, and security behavior.
- MCP docs show every tool with input/output examples.
- Assistant usage docs describe when to call `graph_status`, `repo_summary`, `get_graph_report`, `search_graph`, `search_text`, `get_node`, and `impact_analysis`.
- Known limitations are explicit and honest.

Suggested issues:

- Update README for v0.2.
- Add MCP tool examples.
- Add assistant usage guide.
- Add security and privacy docs.
- Add troubleshooting guide.

## 6. Suggested milestone plan

### Milestone 0: v0.2 planning and backlog

Outcome: v0.2 is decomposed into implementation issues.

Tasks:

- Create umbrella v0.2 issue.
- Create theme labels.
- Create 12 to 16 vertical-slice issues.
- Define release acceptance criteria.
- Define dogfooding targets.

Exit criteria:

- Backlog is ready for agent implementation.
- Each P0 issue has acceptance criteria.

### Milestone 1: Graph correctness foundation

Outcome: graph facts are more stable and explainable.

Tasks:

- Add graph validator.
- Add schema compatibility checks.
- Add edge/evidence normalization.
- Add graph diff report.
- Add node ID stability tests.

Exit criteria:

- Repeated indexing is deterministic.
- Graph validation runs in tests.

### Milestone 2: Resolution, impact, and MCP polish

Outcome: assistant-facing query quality improves.

Tasks:

- Improve import resolution.
- Add resolution strategy metadata.
- Improve impact result grouping.
- Improve reading-order reasons.
- Normalize MCP envelopes and errors.

Exit criteria:

- MCP tools are consistent and evidence-backed.
- Impact and reading order are useful on fixture repos.

### Milestone 3: Update performance and security hardening

Outcome: repeated update/status behavior is safer and faster.

Tasks:

- Add update planner.
- Improve stale detection.
- Add deleted/parse-error cleanup tests.
- Add redaction utility.
- Add path containment and search safety tests.

Exit criteria:

- Update behavior is reliable across changed/new/deleted/parse-error cases.
- Security fixtures pass.

### Milestone 4: Parser abstraction and package awareness

Outcome: parsing and package/config boundaries are more extensible.

Tasks:

- Add parser backend interface.
- Add optional Tree-sitter experiment.
- Improve package root detection.
- Improve workspace/config normalization.

Exit criteria:

- Default parser remains stable.
- Optional Tree-sitter backend can be tested explicitly.
- Package/workspace facts improve on fixture repos.

### Milestone 5: Dogfooding, CI, docs, and release candidate

Outcome: v0.2 is ready to ship.

Tasks:

- Dogfood on selected real repos.
- Convert dogfooding bugs into fixtures.
- Add CI/release smoke checks.
- Update README and MCP docs.
- Write release notes.

Exit criteria:

- v0.2 release checklist passes.
- Known limitations are documented.

## 7. Suggested GitHub issue breakdown

Note: this draft list is input to issue creation, not the final v0.2 backlog. The planning decision log re-slices v0.2 into dependency-ordered vertical issues before GitHub issue creation.

1. Umbrella: RepoLens v0.2 roadmap and release criteria.
2. Add graph validation service and deterministic graph checks.
3. Add schema compatibility and rebuild policy.
4. Add graph diff report for update summaries.
5. Improve Python import and package-root resolution.
6. Improve JS/TS import and deterministic alias resolution.
7. Add resolution strategy metadata and candidate-only fuzzy matching.
8. Improve impact analysis grouping and traversal safety.
9. Improve suggested reading order ranking and reasons.
10. Normalize MCP response envelopes and structured errors.
11. Add incremental update planner and cleanup tests.
12. Add performance benchmark fixtures.
13. Add redaction utility and security fixture suite.
14. Add parser backend interface and optional Tree-sitter experiment.
15. Improve package/workspace/config awareness.
16. Add dogfooding fixture suite and regression process.
17. Add CI/release automation.
18. Update README, MCP docs, assistant usage guide, and known limitations.

## 8. Release acceptance checklist

- [ ] `index` and `update` are deterministic on fixture repos.
- [ ] `status` remains read-like and does not mutate artifacts.
- [ ] Graph schema compatibility is checked.
- [ ] Graph validation runs in tests.
- [ ] Reference resolution includes strategy, confidence, and evidence.
- [ ] Ambiguous queries return candidates.
- [ ] Impact analysis includes dependencies, dependents, tests, docs, configs, commands, and risks where available.
- [ ] MCP tools use consistent envelopes.
- [ ] MCP tools cap and paginate large responses.
- [ ] MCP tools return useful missing-graph and stale-graph responses.
- [ ] Raw text search is sanitized and capped.
- [ ] Secret-looking files are skipped before parsing.
- [ ] Command strings are sanitized and marked as not run.
- [ ] Optional Tree-sitter backend does not affect default install.
- [ ] CI passes lint, format check, typecheck, tests, and build.
- [ ] Docker smoke passes if Docker release path is included.
- [ ] Dogfooding report is complete.
- [ ] Known limitations are documented.

## 9. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Tree-sitter causes install friction | Users avoid v0.2 | Keep Tree-sitter optional behind an extra and flag. |
| Resolver creates false positives | Assistants edit wrong files | Use confidence tiers and candidate-only fuzzy matching. |
| Impact analysis over-reports | Results become noisy | Keep shallow default and prevent upward containment traversal. |
| MCP response shapes drift | Agents become unreliable | Use a shared envelope and contract tests. |
| Update misses stale facts | Graph becomes untrustworthy | Add deleted-file and parse-error cleanup tests. |
| Artifacts expose sensitive metadata | Privacy risk | Add redaction, skip policies, and artifact privacy docs. |
| CI/release work delays product fixes | Slower iteration | Keep automation minimal but mandatory for release candidates. |

## 10. Recommended final v0.2 scope

The strongest v0.2 scope is:

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

Ship v0.2 when graph correctness, resolution, impact analysis, MCP UX, update correctness, safety behavior, and dogfooding confidence are clearly better than v0.1.

Do not ship v0.2 because it has Tree-sitter. Ship it because the default user and assistant experience is more trustworthy.
