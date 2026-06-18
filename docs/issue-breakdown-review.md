# Issue Breakdown Review: RepoLens MCP v0.1

## Source context

This review is based on:

- `repolens-v0.1-prd.md`
- `issue-breakdown.md`
- The intended implementation branch: `feature/repolens-v0.1`
- The `/to-issues` workflow goal: convert the PRD into vertical, agent-ready GitHub Issues with clear blocking relationships.

## Executive verdict

The current issue breakdown is structurally sound and should be kept.

It has the right shape:

- 1 umbrella tracker.
- 13 implementation slices.
- Clear dependency chain from scaffold -> discovery -> storage -> parsers -> update/status -> query service -> MCP -> Docker/docs.
- Coverage for all 76 PRD user stories.

Do not restart the breakdown.

However, do not publish it exactly as-is. It needs a small edit pass before becoming GitHub Issues.

The main issue is that several entries are written as capability summaries, not fully agent-ready implementation cards. Each issue needs acceptance criteria, verification steps, and explicit out-of-scope notes.

## Required changes before publishing

### 1. Add acceptance criteria to every implementation issue

Every issue from 2 to 14 should include this structure:

```md
## Acceptance criteria
- ...

## Tests / verification
- ...

## Out of scope
- ...
```

Reason:

The PRD emphasizes externally observable behavior: CLI output, generated artifacts, graph/query responses, MCP contracts, and filesystem effects. The issue body should make those observable outcomes explicit.

### 2. Fix the blocker for Issue 11

Current:

```md
11. Structured Graph Query Service
Blocked by: 5, 6, 7, 8
```

Recommended:

```md
11. Structured Graph Query Service
Blocked by: 9
```

Acceptable alternative:

```md
11. Structured Graph Query Service
Blocked by: 5, 6, 7, 8, 9
```

Reason:

Issue 11 includes graph status, stale warnings, limits, evidence, and ambiguity behavior. Richer status and staleness classification are introduced in Issue 9, so Issue 11 should not be implemented before Issue 9.

### 3. Treat Issue 1 as a tracker, not an AFK implementation slice

Current:

```md
Type: AFK
```

Recommended:

```md
Type: Tracking / Meta
```

Reason:

The umbrella coordinates the work but does not directly implement product behavior.

### 4. Mark Issue 14 as AFK with a HITL checkpoint

Current:

```md
Type: AFK
```

Recommended:

```md
Type: AFK with HITL checkpoint
```

Reason:

Docker/docs/release readiness can mostly be implemented by an agent, but final release-facing details may require human confirmation:

- Project name/distribution name.
- License wording.
- Whether PyPI publishing is deferred.
- Whether Docker registry publishing is deferred.
- Final README positioning.

### 5. Make Issue 4 more vertical and observable

Issue 4 is currently the most infrastructure-heavy slice. Keep it, but constrain it to a minimum graph store and export flow.

Recommended Issue 4 acceptance criteria:

```md
## Acceptance criteria
- `repolens index <fixture>` creates `.repolens/graph.sqlite`.
- The SQLite database contains schema/version metadata.
- The graph contains repository, directory, file, skip-reason, and run metadata facts.
- The command exports:
  - `.repolens/graph.json`
  - `.repolens/graph-lite.json`
  - `.repolens/graph-report.md`
  - `.repolens/graph-index.md`
  - `.repolens/graph-status.json`
- Full rebuild writes to a temporary database and replaces the graph atomically after success.
- Export files are written through temporary files and atomically replaced.
- Running the same fixture twice produces deterministic exports except explicitly allowed volatile fields.
- Unsupported schema versions produce a clear rebuild-required response.

## Tests / verification
- Add CLI fixture tests proving the artifacts are created.
- Add deterministic export tests.
- Add schema metadata tests.
- Add atomic replacement tests where practical.
- Add no-source-mirroring assertions for AI-facing artifacts.

## Out of scope
- Deep parser facts.
- MCP server.
- Incremental update.
- Full query service.
```

Reason:

Without this constraint, Issue 4 can become a large horizontal storage project.

### 6. Add resolved-decision docs to Issue 2

The PRD says that before implementation, the project should have a resolved-decision document and a vertical-slice implementation plan if those docs do not already exist.

Add this to Issue 2 acceptance criteria:

```md
- Add `docs/repolens-v0.1-decisions.md` summarizing locked implementation decisions from the PRD.
- Add or update `docs/repolens-v0.1-plan.md` with the vertical-slice implementation sequence and dependency map.
```

Reason:

This gives future agents a stable source of truth before they start changing code.

### 7. Treat testing user story 72 as cross-cutting

Do not assign testing mainly to Issue 4 or Issue 14.

Every implementation issue should include the tests for the behavior it introduces.

Examples:

- Issue 3: scanner tests.
- Issue 5: Python parser tests.
- Issue 6: JS/TS parser tests.
- Issue 7: config/command/package/entrypoint parser tests.
- Issue 8: Markdown/comment/agent-guidance tests.
- Issue 9: hashing/status/update classification tests.
- Issue 10: report and raw text search CLI tests.
- Issue 11: query service tests.
- Issue 12: impact analysis and reading-order tests.
- Issue 13: MCP stdio smoke tests.
- Issue 14: Docker and release-readiness smoke tests.

## Recommended final issue list

Keep the issue list mostly unchanged.

### 1. RepoLens MCP v0.1 umbrella tracker

Recommended type:

```md
Type: Tracking / Meta
```

Keep as the parent coordination issue.

It should contain:

```md
## Purpose
Track all RepoLens MCP v0.1 implementation slices.

## Completion criteria
- Issues 2-14 are complete.
- CLI, artifacts, MCP, Docker docs, tests, and release-readiness checks work end to end.
- Deferred features remain clearly documented as out of scope.

## Issue checklist
- [ ] 2. Installable CLI Scaffold With Missing-Graph Status
- [ ] 3. Safe Repository Discovery And Artifact Bootstrap
- [ ] 4. Deterministic Graph Store And Exports
- [ ] 5. Python Structure Indexing End To End
- [ ] 6. JavaScript And TypeScript Structure Indexing End To End
- [ ] 7. Config, Command, Package, And Entrypoint Indexing
- [ ] 8. Markdown, Comments, Docs, And Agent Guidance Indexing
- [ ] 9. Incremental Update And Staleness Classification
- [ ] 10. Report And Safe Raw Text Search CLI
- [ ] 11. Structured Graph Query Service
- [ ] 12. Impact Analysis And Reading Order Queries
- [ ] 13. Read-Only Stdio MCP Server
- [ ] 14. Docker, Assistant Config, And Release Readiness Docs
```

### 2. Installable CLI Scaffold With Missing-Graph Status

Keep.

Add acceptance criteria around:

- `src/repolens` package layout.
- `repolens` console script.
- Typer CLI shell.
- Hatchling packaging.
- Python `>=3.11`.
- pytest, Ruff, mypy configuration.
- `repolens status` works before indexing.
- `status` does not mutate artifacts.
- JSON and text output envelope patterns are established.
- Initial docs:
  - `docs/repolens-v0.1-decisions.md`
  - `docs/repolens-v0.1-plan.md`

Out of scope:

- Real scanner.
- Graph database.
- MCP server.
- Parser extraction.

### 3. Safe Repository Discovery And Artifact Bootstrap

Keep.

Add acceptance criteria around:

- Analysis root containment.
- Repo-relative POSIX paths.
- `.gitignore` honoring.
- Built-in excludes.
- Secret-file skip policy.
- Binary/media skip policy.
- Size caps.
- Symlink behavior.
- Non-Git directory support.
- `.repolens/.gitignore`.
- RepoLens never scans `.repolens`.
- Skipped paths are recorded with sanitized reasons.

Out of scope:

- Deep parsing.
- Graph database schema beyond what Issue 4 owns.
- MCP.

### 4. Deterministic Graph Store And Exports

Keep, but make it explicitly minimum viable graph storage and deterministic export.

Use the Issue 4 acceptance criteria from the earlier section.

### 5. Python Structure Indexing End To End

Keep.

Add acceptance criteria around:

- Python AST extraction.
- Functions.
- Async functions.
- Classes.
- Methods.
- Imports.
- Decorators.
- Inheritance metadata.
- Tagged comments.
- Shallow same-module calls only where high confidence.
- Python stdlib vs third-party classification.
- Local import root inference.
- Syntax errors are nonfatal and clear stale graph facts for that file.

Out of scope:

- Deep semantic call graph.
- Runtime import execution.
- AI/LLM analysis.

### 6. JavaScript And TypeScript Structure Indexing End To End

Keep.

Add acceptance criteria around:

- `.js`, `.jsx`, `.ts`, `.tsx`, module extensions.
- Imports.
- Exports.
- Obvious top-level functions.
- Classes.
- Interfaces.
- Type aliases.
- CommonJS assignments where clear.
- Package-name normalization.
- Node built-ins separated from third-party packages.
- Deterministic simple TypeScript alias resolution.

Out of scope:

- Tree-sitter.
- TypeScript compiler integration.
- Full module resolution.
- Deep framework analysis.

### 7. Config, Command, Package, And Entrypoint Indexing

Keep.

Add acceptance criteria around:

- `pyproject.toml`.
- legacy Python packaging files.
- `requirements*.txt`.
- `package.json`.
- lockfile detection without deep lockfile parsing.
- Dockerfile shallow parsing.
- Makefile/task file shallow parsing.
- GitHub Actions shallow parsing.
- pre-commit config shallow parsing.
- candidate verification commands marked as not run.
- command sanitization.
- package manager detection.
- entrypoint detection from strong evidence.

Out of scope:

- Executing commands.
- Deep shell/YAML/Docker semantic evaluation.
- Runtime package registry lookups.

### 8. Markdown, Comments, Docs, And Agent Guidance Indexing

Keep.

Add acceptance criteria around:

- README title and short intro extraction.
- Markdown headings.
- Duplicate heading IDs.
- Links to resolvable local files.
- Exact path mentions.
- Code-fence metadata without copying code block bodies.
- Tagged comments: TODO, FIXME, RISK, SECURITY.
- Agent instruction files classified as important Markdown.
- Skill manifests parsed shallowly.

Out of scope:

- Full Markdown content mirroring.
- PDF/image/video parsing.
- Untagged routine comment graph nodes.

### 9. Incremental Update And Staleness Classification

Keep.

Add acceptance criteria around:

- `repolens update`.
- No graph exists -> bootstrap behavior like `index` with clear initialization report.
- Raw hash.
- Normalized hash.
- Graph hash.
- Git branch/commit stale signal.
- Config hash stale signal.
- Extractor/parser version invalidation.
- Change classifications:
  - deleted
  - new
  - parse error
  - dependency change
  - structural change
  - content-only change
  - no change
- Secondary signals preserve detail.
- Blank-line-only/content-only behavior is observable.
- Path-based file identity.
- Rename represented as delete plus new.

Out of scope:

- Rename detection.
- Historical graph snapshots.
- Watch mode.
- Git hooks.

### 10. Report And Safe Raw Text Search CLI

Keep.

Add acceptance criteria around:

- `repolens report` reads existing report by default.
- Regeneration from graph store is explicit.
- CLI `search` means raw text search, not structured graph search.
- Search uses same scan safety policy.
- Query must be non-empty.
- Results are capped.
- Results are sanitized.
- Case-insensitive default.
- Optional case-sensitive mode only if simple.
- No whole-file output.
- Secret-looking files remain excluded.

Out of scope:

- MCP search tools.
- Structured graph search CLI.
- Regex unless safely implemented.

### 11. Structured Graph Query Service

Change blocker to Issue 9.

Add acceptance criteria around framework-independent query service methods for:

- `repo_summary`
- `graph_status`
- `get_graph_report`
- `search_graph`
- `get_node`
- `get_neighbors`
- `shortest_path`
- `list_entrypoints`

Also include:

- Confidence fields.
- Evidence fields.
- Limits.
- Stale warnings.
- Ambiguity handling.
- Pagination/truncation metadata.
- Missing graph responses.
- No source-file read behavior.

Out of scope:

- MCP protocol wrapper.
- Raw text search implementation if already owned by Issue 10.
- Impact analysis and reading order, which are owned by Issue 12.

### 12. Impact Analysis And Reading Order Queries

Keep.

Add acceptance criteria around:

- `impact_analysis`.
- `suggest_reading_order`.
- Direct affected files.
- Likely affected files.
- Dependencies.
- Dependents.
- Likely tests.
- Related docs.
- Related configs.
- Risk/tagged comments.
- Candidate verification commands.
- Evidence and confidence.
- Caps and truncation.
- Ambiguous target handling.

Out of scope:

- Runtime coverage claims.
- AI ranking.
- Embeddings.
- Source-code editing.

### 13. Read-Only Stdio MCP Server

Keep.

Add acceptance criteria around:

- `repolens mcp`.
- Official Python MCP SDK.
- stdio server does not write logs/progress to stdout.
- Exposes exactly these v0.1 tools:
  - `repo_summary`
  - `graph_status`
  - `get_graph_report`
  - `search_graph`
  - `search_text`
  - `get_node`
  - `get_neighbors`
  - `shortest_path`
  - `impact_analysis`
  - `suggest_reading_order`
  - `list_entrypoints`
- All tools are read-only.
- Missing graph responses are structured and actionable.
- Success responses use a consistent envelope.
- Error responses use structured payloads.
- Response caps and truncation metadata are enforced.
- Live graph status uses a short TTL cache.
- MCP smoke test starts server, lists tools, and calls representative tools.

Out of scope:

- Write-capable MCP tools.
- HTTP MCP/API serving.
- Source-file read tools.
- Graph update tools.

### 14. Docker, Assistant Config, And Release Readiness Docs

Recommended type:

```md
Type: AFK with HITL checkpoint
```

Keep.

Add acceptance criteria around:

- Dockerfile using slim Python image matching supported baseline.
- Docker examples use `repolens:latest`.
- Docker entrypoint is `repolens`.
- Host user mapping example avoids root-owned generated artifacts.
- Docker runtime does not require network access for normal indexing/MCP.
- Native install docs include `pipx` and/or `uv tool`.
- OpenCode MCP config example.
- README quickstart.
- README security behavior.
- README artifact privacy warning.
- README config sample.
- README MCP tool usage.
- README assistant prompt guidance.
- README roadmap with deferred features.
- Manual dogfooding checklist.

Out of scope:

- PyPI publishing.
- Docker registry publishing.
- Final license/legal decision unless the human confirms it.

## Recommended publishing note

Add this near the top of `issue-breakdown.md` before creating GitHub Issues:

```md
Publishing guidance:
- Create the umbrella tracker first.
- Publish issues 2-14 as vertical implementation slices.
- Every issue must include acceptance criteria, tests/verification, and out-of-scope notes.
- Story 72 is cross-cutting: each implementation issue owns tests for the behavior it introduces.
- Use area-prefixed commits and reference the issue number after issues are created.
- Do not expand v0.1 scope beyond the PRD.
```

## Final dependency graph

Recommended dependency graph:

```text
1 umbrella tracker
└── 2 CLI scaffold + missing graph status
    └── 3 safe discovery + artifact bootstrap
        └── 4 graph store + deterministic exports
            ├── 5 Python indexing
            ├── 6 JS/TS indexing
            ├── 7 config/command/package/entrypoint indexing
            └── 8 Markdown/comment/agent guidance indexing
                └── 9 incremental update + staleness classification
                    └── 11 structured graph query service
                        └── 12 impact analysis + reading order
                            └── 13 read-only stdio MCP server
                                └── 14 Docker/config/docs/release readiness

10 report + safe raw text search CLI
└── blocks 13
```

More precise form:

```text
2 -> 3 -> 4
4 -> 5
4 -> 6
4 -> 7
4 -> 8
5,6,7,8 -> 9
4 -> 10
9 -> 11
11 -> 12
10,11,12 -> 13
13 -> 14
```

## Summary for implementation assistant

Apply this review to `issue-breakdown.md` before publishing issues.

Required edits:

1. Change Issue 1 type from `AFK` to `Tracking / Meta`.
2. Add acceptance criteria, tests/verification, and out-of-scope sections to Issues 2-14.
3. Change Issue 11 blocker from `5, 6, 7, 8` to `9`.
4. Add resolved-decision and vertical-slice plan docs to Issue 2.
5. Tighten Issue 4 to minimum graph store plus deterministic exports.
6. Treat story 72 as cross-cutting tests across all issues.
7. Mark Issue 14 as `AFK with HITL checkpoint`.
8. Keep the same overall 1 + 13 issue structure.
9. Do not merge issues.
10. Only split Issue 4 if it becomes too large during implementation planning.
