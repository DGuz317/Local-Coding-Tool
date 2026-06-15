# PRD: RepoLens MCP v0.1

## Problem Statement

AI coding assistants repeatedly rediscover the same repository structure every time they work in a codebase. They list files, search text, open many files, infer entrypoints, guess related tests, and often still miss important configuration, agent instructions, package roots, or dependency relationships.

For medium and large repositories, this wastes tokens and time. It also makes assistants less reliable because each session starts from raw exploration instead of a structured, reusable repo map.

The current codebase is only a minimal Python stub. There is no RepoLens package, CLI, scanner, graph store, MCP server, Docker support, test setup, lint/typecheck setup, or generated repo graph artifact pipeline yet.

## Solution

Build RepoLens MCP v0.1 as a local-first repository intelligence backend.

From the user's perspective, RepoLens should let them run a local CLI against a repository, generate `.repolens` graph artifacts, and expose read-only query tools through a local stdio MCP server. An AI assistant can then ask RepoLens for repo summary, graph status, entrypoints, important files, related tests, impact analysis, and task-specific reading order before opening source files.

The first version should be deterministic, local, safe by default, and Docker-friendly. It should not require cloud services, network access during normal indexing, AI models, embeddings, or a browser UI.

## User Stories

1. As a developer, I want to run a single local command to index a repository, so that I can create reusable repo context for AI assistants.
2. As a developer, I want RepoLens to create local graph artifacts under `.repolens`, so that repo intelligence is available without a hosted service.
3. As a developer, I want generated artifacts to be ignored by Git by default, so that indexing does not dirty my repository with generated files.
4. As a developer, I want a full rebuild command, so that I can intentionally regenerate the repo graph from scratch.
5. As a developer, I want an incremental update command, so that repeated indexing after edits is faster.
6. As a developer, I want a read-like status command, so that I can see whether the graph is stale without mutating artifacts.
7. As a developer, I want status to report missing artifacts clearly, so that first-run setup is obvious.
8. As a developer, I want status to report Git branch or commit changes, so that assistants know when context may be stale after checkout or commit changes.
9. As a developer, I want RepoLens to detect blank-line-only edits, so that raw file changes are visible without falsely claiming dependency graph changes.
10. As a developer, I want RepoLens to distinguish content-only, structural, dependency, new, deleted, and parse-error changes, so that I understand what kind of update occurred.
11. As a developer, I want change reports to include secondary signals, so that a dependency change can still show that raw content and symbols changed too.
12. As a developer, I want RepoLens to skip generated, dependency, cache, build, and virtual environment folders by default, so that indexing stays fast and relevant.
13. As a developer, I want RepoLens to honor `.gitignore`, so that ignored files are not accidentally indexed as source context.
14. As a developer, I want RepoLens to skip likely secret files by default, so that `.env` files, keys, and credential files are not read into artifacts.
15. As a developer, I want RepoLens to sanitize secret-like metadata and command strings, so that generated artifacts do not expose tokens or passwords.
16. As a developer, I want RepoLens to enforce repo-root path containment, so that MCP tools and scanners cannot read outside the target repository.
17. As a developer, I want RepoLens to skip oversized files by default, so that large generated or binary artifacts do not dominate indexing time.
18. As a developer, I want RepoLens to detect binary and media files safely, so that it does not attempt to parse non-source content.
19. As a developer, I want skipped files and directories to be logged with reasons, so that I can understand why expected files are missing from the graph.
20. As a developer, I want RepoLens to work on non-Git directories, so that I can index extracted folders or sample projects too.
21. As a developer, I want paths in artifacts to be repo-relative and portable, so that artifacts work across machines, Docker, and operating systems.
22. As a developer, I want source locations to include line ranges, so that assistants can open targeted files and symbols efficiently.
23. As a Python developer, I want RepoLens to extract Python functions, async functions, classes, methods, imports, decorators, inheritance metadata, and tagged comments, so that assistants can understand Python code structure.
24. As a JavaScript or TypeScript developer, I want RepoLens to extract imports, exports, top-level functions, classes, interfaces, and type aliases where clear, so that assistants can understand common JS and TS surfaces.
25. As a JavaScript or TypeScript developer, I want RepoLens to understand common JS/TS extensions, so that `.jsx`, `.tsx`, module files, and TypeScript files are represented.
26. As a JavaScript or TypeScript developer, I want Node built-ins to be classified separately from third-party packages, so that dependency reports are not noisy.
27. As a TypeScript developer, I want simple path aliases to resolve when deterministic, so that common local imports do not appear as unknown external packages.
28. As a Python developer, I want local import roots inferred from package metadata and common layouts, so that source imports can resolve without manual config.
29. As a developer, I want external packages to include both declared dependencies and observed imports, so that I can see what the repo declares and what source files use.
30. As a developer, I want Python standard-library imports separated from third-party imports, so that dependency reports are accurate.
31. As a developer, I want lockfiles detected but not deeply parsed, so that package manager context is available without graph bloat.
32. As a developer, I want requirements files shallowly parsed, so that Python dependencies are detected in older projects.
33. As a developer, I want known configuration files parsed for commands, package roots, dependencies, and tooling, so that RepoLens can recommend relevant verification commands.
34. As a developer, I want arbitrary JSON, YAML, and TOML files represented shallowly, so that config files are discoverable without exploding the graph.
35. As a developer, I want Dockerfiles parsed shallowly, so that container entrypoint and build clues are visible.
36. As a developer, I want Makefiles and task files parsed shallowly, so that common test, lint, build, and dev commands are discoverable.
37. As a developer, I want GitHub Actions and pre-commit configs parsed safely, so that CI and tooling signals are visible without executing anything.
38. As a developer, I want candidate verification commands marked as not run, so that assistants do not mistake inferred commands for verified safe commands.
39. As a developer, I want commands grouped by package or config root, so that monorepo command context is clear.
40. As a developer, I want package managers detected from lockfiles and config, so that command guidance can use the right ecosystem language.
41. As a developer, I want README metadata and headings extracted, so that repo purpose and documentation structure are visible without copying entire docs.
42. As a developer, I want Markdown headings and links represented, so that documentation can connect to files and modules when explicit.
43. As a developer, I want exact path mentions in Markdown to link to files when resolvable, so that docs-to-code relationships are available.
44. As a developer, I want tagged comments such as TODO, FIXME, RISK, and SECURITY surfaced, so that assistants can see important maintenance and risk annotations.
45. As a developer, I want routine untagged comments to stay out of the graph by default, so that reports remain focused.
46. As a developer using agent instruction files, I want RepoLens to identify agent instructions and skills, so that AI assistants see repo-specific guidance early.
47. As an AI coding assistant, I want a compact graph report, so that I can orient myself before opening source files.
48. As an AI coding assistant, I want a compact machine-readable graph summary, so that I can ingest repo context efficiently.
49. As an AI coding assistant, I want a graph index with important files, symbols, modules, tests, configs, packages, commands, and tagged comments, so that I can jump to relevant context quickly.
50. As an AI coding assistant, I want graph freshness metadata in every artifact, so that I can avoid making decisions from stale context.
51. As an AI coding assistant, I want a repo summary MCP tool, so that I can query high-level context without scanning the filesystem.
52. As an AI coding assistant, I want a graph status MCP tool, so that I can know whether the graph is stale before relying on it.
53. As an AI coding assistant, I want an MCP tool to read the graph report, so that I can get the primary orientation artifact through MCP.
54. As an AI coding assistant, I want structured graph search, so that I can find files, modules, symbols, commands, packages, comments, headings, and config facts.
55. As an AI coding assistant, I want raw text search with capped sanitized results, so that I can find exact text without reading whole files.
56. As an AI coding assistant, I want a get-node tool, so that I can inspect a specific graph entity by ID or disambiguated query.
57. As an AI coding assistant, I want a neighbors tool, so that I can explore nearby graph relationships around a file, symbol, module, command, or package.
58. As an AI coding assistant, I want shortest-path analysis, so that I can understand how two concepts or nodes are connected when the graph has evidence.
59. As an AI coding assistant, I want impact analysis, so that I can see likely affected files, dependencies, dependents, tests, docs, risks, and candidate verification commands before editing.
60. As an AI coding assistant, I want suggested reading order for a task, so that I can open the smallest useful set of files first.
61. As an AI coding assistant, I want entrypoint listing, so that I can identify CLIs, app starts, scripts, Docker entrypoints, and package-defined commands.
62. As an AI coding assistant, I want MCP responses to include confidence, evidence, limits, and stale warnings, so that I can avoid over-trusting shallow static analysis.
63. As an AI coding assistant, I want ambiguous searches to return candidates instead of silently choosing, so that I do not act on the wrong file or symbol.
64. As a team, I want generated graph answers to be deterministic and local, so that the tool is trustworthy and reproducible.
65. As a team, I want no AI model requirement for core graph generation, so that RepoLens works offline and without provider setup.
66. As a team, I want no runtime network calls, so that indexing can run in secure or offline environments.
67. As a team, I want no telemetry, so that repo metadata stays local.
68. As a team, I want Docker support, so that users can run RepoLens without installing Python locally.
69. As a team, I want Docker examples to avoid root-owned generated artifacts, so that mounted repos remain editable by the host user.
70. As a team, I want a native install path, so that developers can use RepoLens as a normal CLI tool.
71. As a team, I want OpenCode MCP configuration examples, so that users can connect RepoLens to an AI coding assistant quickly.
72. As a maintainer, I want tests around scanner behavior, hashing, parser extraction, artifacts, query service, MCP smoke, and Docker release smoke, so that v0.1 behavior is protected.
73. As a maintainer, I want linting and type checking configured, so that future agents can modify the codebase safely.
74. As a maintainer, I want schema and version metadata in artifacts, so that incompatible graphs can be detected and rebuilt.
75. As a maintainer, I want parser or config version changes to force reparse, so that unchanged files do not keep stale graph facts after upgrades.
76. As a maintainer, I want release readiness criteria, so that v0.1 is not considered done until CLI, artifacts, MCP, Docker, docs, and checks all work end-to-end.

## Implementation Decisions

- RepoLens MCP v0.1 will deliver the full local assistant loop: CLI commands, local indexing and updating, generated graph artifacts, read-only stdio MCP tools, Docker support, README, OpenCode example, and tests.
- The v0.1 CLI surface will include implemented commands only: `index`, `update`, `status`, `report`, `search`, and `mcp`.
- HTTP serving, watch mode, Git hooks, interactive visualization, AI enrichment, embeddings, Graphify import/export, write-capable MCP tools, and deep semantic call graphs are deferred.
- The current stub project will be renamed cleanly to the RepoLens package and CLI identity. No backward compatibility is needed for the existing stub identity.
- The Python runtime baseline will be `>=3.11`. Local development may use newer Python versions as long as compatibility is preserved.
- The package will use a standard source-layout Python package with a console script named `repolens`.
- Typer will provide the user-facing CLI. CLI handlers should stay thin and delegate to framework-independent services.
- The official Python MCP SDK will provide the stdio MCP server. The FastMCP/decorator-style layer is acceptable for v0.1 as long as query logic remains independent.
- Runtime dependencies should remain minimal and use compatible version ranges. Development dependencies should be grouped separately.
- The build backend will be Hatchling.
- CLI output defaults to concise plain text. Machine-readable output uses a JSON envelope where practical.
- CLI commands should support verbose output for diagnostics. Quiet mode is optional if simple.
- `index` performs a full deterministic rebuild of known generated artifacts.
- `update` performs incremental file detection and reparses changed files when possible. If no graph exists, it bootstraps like `index` and reports initialization clearly.
- `status` is read-like and does not mutate graph artifacts. It computes a lightweight live freshness overlay using metadata first and selective hashing when needed.
- Missing artifacts make `status` report stale with a recommended action instead of failing by default.
- `status --fail-if-stale` may be added for automation if simple.
- `report` prints the existing graph report by default. Regeneration from the graph store must be explicit.
- CLI `search` means raw text search. Structured graph search is exposed through MCP and may get a separate CLI surface later.
- `.repolens` is the standard artifact directory under the analysis root.
- `.repolens` is local cache by default and should include an internal `.gitignore` that ignores generated contents without modifying the root ignore file.
- RepoLens must never scan `.repolens` itself.
- RepoLens should not delete unknown files inside `.repolens`. It may replace known generated artifacts atomically and clean its own stale temp files.
- `graph.sqlite` is the authoritative store after graph storage exists.
- JSON, Markdown, status, and report artifacts are deterministic exports derived from SQLite.
- The graph store keeps the current graph plus run summaries and latest change status, not full historical snapshots.
- SQLite should use normalized fields for common queries and JSON metadata for parser-specific details. Core queries should not require SQLite JSON functions.
- Core graph tables should be supported by helper tables for commands, packages, modules, and changes where useful.
- Commands, packages, and modules should also exist as graph nodes, keyed consistently with helper rows.
- SQLite foreign keys should be enabled for mutating connections.
- Default SQLite journal behavior is sufficient initially. WAL mode is deferred unless concurrent-read testing proves it necessary.
- Full rebuilds should build a temporary database and replace atomically after success. Incremental updates should use transactions.
- Export files should be written to temporary files and atomically replaced.
- MCP reads should see either the previous complete graph or the new complete graph, never partially written exports.
- Graph artifacts include version, schema, extractor, timestamp, Git, config hash, and scan provenance where available.
- Unsupported schema versions trigger a rebuild in v0.1 rather than migrations.
- Parser or extractor version changes should force reparse of unchanged files because graph facts may change.
- Effective config changes should force a full scan/reparse.
- Configuration should be optional and versionable at the repo root, with Python project config as a fallback where appropriate.
- Configuration validation should be strict for RepoLens config because scan safety and limits depend on it.
- RepoLens should not create a root config file automatically. Docs should provide a sample config.
- User patterns should use Git-style pathspec semantics against repo-relative POSIX paths.
- Include patterns may override ordinary default excludes but must not bypass path containment or secret-file safety in v0.1.
- No unsafe include-secrets option should exist in v0.1.
- File discovery scans any existing readable directory. It does not require Git.
- The provided path is the analysis root. RepoLens should not silently expand to a Git root.
- Paths in artifacts and MCP responses should be repo-relative POSIX-style paths, preserving discovered casing and Unicode.
- Absolute paths stay internal unless an MCP input absolute path resolves inside the analysis root and is normalized to a repo-relative path.
- Symlinks must never escape the analysis root. Internal symlinks are not traversed in v0.1 and are logged as skipped metadata.
- Default scan policy honors `.gitignore`, built-in excludes, size caps, binary detection, generated-file hints, and secret path patterns.
- Default excludes include common VCS, dependency, build, cache, virtual environment, generated, and graph-output folders.
- Useful dot-directories such as agent metadata and GitHub workflows should not be excluded just because they start with a dot.
- Secret-looking files are skipped by path/name before parsing. Content secret scanning is out of scope for v0.1.
- Secret-like metadata and command values should be sanitized before being written to artifacts or logs.
- Skipped secret-like files should be reported by count and sanitized path only, never by content or hash.
- Oversized skipped files are not fully hashed by default. They are recorded with metadata and skip reason.
- Binary/media/archive files are skipped early by extension and content sniffing.
- Common text lockfiles are represented as important metadata/config files, but their contents are not deeply parsed.
- Generated-looking files are marked and deprioritized instead of always skipped, unless they are clearly huge, minified, or artifact-like.
- Raw hashes use exact bytes. Normalized hashes decode text, normalize line endings, trim trailing whitespace, collapse blank-line runs, and preserve leading indentation.
- A newly inserted single blank line may change the normalized hash. If graph facts are unchanged, the primary change type remains content-only.
- Graph hashes are computed from canonical sorted graph facts, excluding volatile fields such as parser duration and line shifts.
- Line-range-only shifts caused by whitespace are content-only changes with a line-range signal.
- Primary change classification follows precedence: deleted, new, parse error, dependency change, structural change, content-only change, no change. Secondary signals preserve detail.
- File identity is path-based in v0.1. Renames are represented as delete plus new.
- No duplicate file detection is needed in v0.1.
- Git metadata should be read directly when possible, including simple Git worktrees and packed refs. Git subprocess fallback is not required by default.
- Detectable Git branch or commit changes make the graph stale.
- Submodule files under the analysis root may be indexed like normal files. `.gitmodules` is metadata. Nested Git internals are skipped.
- Python parsing uses the standard AST where valid and extracts core symbols, imports, decorator metadata, inheritance metadata, tagged comments, and shallow same-module calls where high confidence.
- Python AST syntax errors remove stale graph facts for that file and record parse error state nonfatally.
- JS and TS parsing stays pure Python in v0.1, using bounded line/regex scanners for imports, exports, obvious top-level symbols, TypeScript interfaces, and type aliases.
- Tree-sitter and Node-based parser dependencies are deferred.
- JS and TS external imports normalize to package roots while preserving full specifiers as metadata.
- Python imports use top-level import names for observed package identity. Comprehensive import-name to distribution-name mapping is deferred.
- Python stdlib and Node built-ins are classified separately from third-party packages.
- Simple TypeScript alias resolution from config is supported only when deterministic.
- Framework entrypoint detection is lightweight and evidence-backed. Deep route extraction is deferred.
- Route-like facts are metadata/entrypoint hints in v0.1, not first-class route graph coverage.
- Markdown parsing extracts headings, heading hierarchy, short README intro, code-fence metadata, tagged comments, relative links to existing files, and exact path mentions when resolvable.
- Markdown code block contents and full README text should not be copied into graph artifacts.
- Tagged comment detection applies across supported text languages using leading tags from the default tag list.
- Tagged comments become graph nodes. Routine untagged comments remain searchable through live text search but are not emitted as default graph nodes.
- Comment node IDs should be stable across line shifts by using path, tag, content hash, and nearest enclosing symbol when available.
- Agent instruction files are classified as important Markdown files. Skill manifests get shallow skill nodes with basic metadata.
- Config parsing focuses deeply only on known project/tool configs. Arbitrary JSON/YAML/TOML stores sanitized top-level keys as metadata.
- YAML parsing must use safe loading only. Custom-tag or malformed config failures are nonfatal except invalid RepoLens config.
- Dockerfiles, Makefiles, package manifests, CI workflows, pre-commit config, Python package files, requirements files, and task files are parsed shallowly for relevant facts.
- Candidate verification commands should be purpose-classified but never called safe. They are detected and not run.
- Command strings must be sanitized. Deploy/publish-like commands should not be recommended for automatic execution.
- Entrypoints are detected from strong evidence first: Python main guards, package scripts and bin fields, console scripts, Docker CMD/ENTRYPOINT, shebang/executable scripts, and lightweight framework evidence.
- Entry points include confidence and evidence.
- Modules are coarse logical areas inferred from package roots, source roots, and meaningful top-level areas, not one module per file.
- Symbols are represented by specific node kinds such as function, class, method, interface, and type alias. `Symbol` is a query category, not a duplicate node type.
- Node IDs are deterministic, readable, path-plus-qualified-name IDs where possible. Line numbers are metadata, not primary identity.
- Repository and directory node IDs should avoid absolute paths.
- Markdown section IDs use file-scoped slugs with duplicate suffixes.
- Commands use source-based IDs. Packages use scoped local/external ecosystem IDs. Modules use path-based IDs.
- Imports are primarily stored as metadata and dependency/reference edges. Separate import nodes are optional only if they add clear value.
- Edge directions use active source-to-target semantics.
- `IMPORTS` represents raw import evidence. `DEPENDS_ON` represents resolved or derived dependency relationships.
- `REFERENCES` represents code/config references. `MENTIONS` is reserved for sparse exact prose/comment references.
- `CONFIGURES` links config files to known commands, packages, tools, and entrypoints, not every arbitrary key.
- `ENTRYPOINT_FOR` links an entrypoint file or command to the repository, package, or runtime context it starts.
- Duplicate logical edges should be merged with aggregated evidence. Edge summary confidence uses the highest evidence confidence.
- Evidence entries are structured and compact, with source, path, optional line range, detail, and confidence. They do not include full source snippets by default.
- Confidence exposed to users is categorical: high, medium, or low. Numeric weights may remain internal.
- Reports are deterministic and evidence-based. Unknown sections should say not detected rather than inventing prose.
- Repository purpose comes only from explicit package metadata, README title/intro, or repository name.
- Static hotspots are heuristic and must be labeled as static, with reasons such as import centrality, symbol count, tagged comments, parser errors, or many test links.
- Module summaries are structured fact summaries, not semantic prose.
- Graph JSON has explicit deterministic sections and does not include full source code.
- Full graph JSON is not size-capped by default beyond scan policy. AI-facing artifacts and MCP responses are capped.
- Lite JSON is a compact dual-use artifact with stable keys, capped arrays, reasons, evidence, and freshness.
- Graph report is the primary first-read artifact for assistants. Lite JSON is the compact structured companion.
- Graph index is a capped table-oriented lookup artifact, not a full source mirror.
- JSON artifacts use UTF-8, readable 2-space formatting, and deterministic ordering where helpful.
- No compressed graph exports are needed in v0.1.
- MCP tool names should exactly match the resolved v0.1 contract: `repo_summary`, `graph_status`, `get_graph_report`, `search_graph`, `search_text`, `get_node`, `get_neighbors`, `shortest_path`, `impact_analysis`, `suggest_reading_order`, and `list_entrypoints`.
- MCP v0.1 is read-only. It does not update graphs, modify files, execute commands, or read whole source files.
- MCP can start before indexing. Tools should return actionable missing-graph responses instead of causing a generic connection failure.
- MCP stdio mode must not write logs or progress to stdout.
- MCP expected errors should use structured error payloads. Success responses should use a consistent envelope with data, freshness, warnings, limits, and truncation metadata.
- MCP graph status computes a live read-only freshness overlay with a short TTL cache.
- MCP artifact responses are capped and explicitly marked if truncated.
- `get_graph_report` may return an existing report with a warning if SQLite is missing. DB-backed graph tools require SQLite.
- Structured graph search searches graph metadata only, not raw source text or embeddings.
- Raw text search reads currently eligible files live using the same scan safety policy. It requires a non-empty query and returns only capped sanitized matching line previews.
- Search is case-insensitive by default, with case-sensitive options. Regex is optional/deferred unless safely implemented.
- List and search tools use limit/offset-style pagination with truncation metadata.
- `get_node`, `shortest_path`, `impact_analysis`, and reading-order target resolution should disambiguate close matches instead of silently choosing.
- `get_neighbors` defaults to shallow traversal, supports filters, and caps depth.
- `shortest_path` resolves fuzzy inputs through graph search and uses bounded priority-ordered BFS with edge type filters.
- `impact_analysis` returns direct and likely affected context, including dependencies, dependents, tests, docs, configs, nearby risk comments, shallow calls where available, and candidate verification commands.
- `suggest_reading_order` uses deterministic token heuristics, identifier splitting, evidence, and reasons. It defaults to a small set of files.
- `suggest_reading_order` should include likely tests when relevant and config files only when task-relevant.
- Test relationships use conservative deterministic heuristics: direct imports when available, path/name similarity with lower confidence, and no runtime coverage claims.
- Docker uses an official slim Python image matching the minimum supported baseline.
- Docker image examples use a local `repolens:latest` tag and entrypoint `repolens`.
- Docker docs should show host user mapping to avoid root-owned generated artifacts.
- Docker runtime should not require network access for normal indexing or MCP serving.
- Native install docs should prioritize CLI tool installation through `pipx` or `uv tool`, while keeping normal package installation for contributors.
- Initial distribution is Git/local source-first. PyPI and Docker registry publishing are release decisions after name, license, and ownership are settled.
- The CLI/import name remains `repolens` even if the eventual distribution name changes.
- The product name in docs is RepoLens MCP, with no legal/trademark claim.
- README should start with native quickstart, then Docker, then OpenCode and generic MCP stdio configuration.
- README should document security behavior, artifact privacy, config sample, MCP tool usage, assistant prompt guidance, and short roadmap.
- OpenCode configuration should live as an example and not as active repo configuration.
- The roadmap should clearly list deferred features separately from v0.1 promises.
- The branch for implementation should be `feature/repolens-v0.1`.
- Slice commits should use concise area-prefixed messages and reference GitHub issues after they exist.
- The GitHub backlog should include an umbrella v0.1 issue plus roughly 10 to 14 vertical-slice implementation issues.

## Testing Decisions

- Tests should verify external behavior rather than implementation details. Assertions should focus on CLI outputs, generated artifacts, graph/query responses, MCP tool contracts, and observable file-system effects.
- The highest useful seam for most indexing behavior is the CLI command operating on temporary fixture repositories.
- The highest useful seam for graph querying is a framework-independent query service backed by generated graph storage.
- MCP should be tested mostly through query-service behavior plus a small stdio protocol smoke test that starts the server, lists tools, and calls one or two representative tools if practical.
- Docker should not be required for normal unit tests. Docker build/run and Docker MCP smoke are release-prep or CI-optional checks.
- Most fixture repositories should be created dynamically in tests using temporary directories. Small static fixtures are acceptable only when they improve readability.
- Release acceptance should include at least a Python fixture, a JS/TS fixture, and a mixed docs/config fixture, plus manual dogfooding on this repository.
- Scanner tests should cover path containment, `.gitignore` handling, default excludes, secret-file skips, size caps, binary skips, generated-file marking, symlink behavior, language detection, and skip reasons.
- Hashing and status tests should cover raw hash changes, normalized hash behavior, graph hash stability, blank-line changes, line-range-only shifts, new files, deleted files, parse errors, Git metadata changes, config hash changes, and missing artifacts.
- SQLite tests should verify schema metadata, file nodes, directory containment edges, foreign key consistency, transactions, current-graph replacement, deleted-file cleanup, version metadata, and authoritative export behavior.
- Export tests should verify required artifacts are produced, deterministic ordering, provenance metadata, freshness metadata, capped AI-facing sections, no source-code mirroring, and atomic replacement behavior where feasible.
- Python parser tests should cover imports, functions, async functions, classes, methods, decorators, inheritance metadata, tagged comments, docstring first-sentence extraction, shallow calls, syntax errors, and parse-error graph cleanup.
- Config parser tests should cover package metadata, dependencies, commands, command redaction, command purpose classification, package roots, entrypoint hints, lockfile detection, package-manager detection, safe YAML behavior, malformed config behavior, Dockerfiles, Makefiles, CI workflows, pre-commit config, and legacy Python packaging files.
- JS/TS parser tests should cover supported extensions, imports, exports, CommonJS assignments, top-level symbols, interfaces, type aliases, package-name normalization, Node built-ins, simple aliases, unresolved imports, and parser limitations.
- Markdown/comment tests should cover headings, duplicate heading IDs, README title/intro, local links, exact path mentions, code-fence metadata without code body storage, tagged comments, block comment tags, agent instruction classification, and skill nodes.
- Text search tests should cover eligible-file policy, secret skip policy, non-empty query requirement, case-insensitive default, truncation, sanitization, result caps, optional case sensitivity, and no whole-file reads.
- Graph search tests should cover structured fields only, exact/path/name ranking, token matching, public-symbol prioritization, evidence, limits, and ambiguity behavior.
- Query tool tests should cover repo summary, graph status, node lookup, neighbors, entrypoints, shortest path, impact analysis, reading order, stale warnings, confidence, evidence, and truncation.
- CLI tests should cover `--json` envelopes, human summaries, nonzero operational errors, parser-error warnings with exit 0, missing graph status behavior, and optional stale-as-failure behavior.
- MCP tests should cover read-only behavior, missing graph responses, stdout discipline for stdio mode, structured success/error envelopes, live status TTL behavior, and response limits.
- Quality checks should use pytest, Ruff check, Ruff format check, and mypy once the project scaffold exists.
- Mypy should start pragmatically on the application package rather than full strict mode on day one.
- Ruff should start with conservative lint/format rules rather than aggressive style enforcement.
- Package release prep should include isolated install smoke tests, package build verification, Docker index smoke, and Docker MCP smoke where practical.
- There is no prior test suite in the current codebase. The initial tests will establish the testing seams rather than extending existing tests.

## Out of Scope

- Hosted cloud dashboard.
- User accounts.
- Team permissions.
- Cloud sync or hosted storage.
- Browser UI.
- Interactive graph visualization.
- HTTP MCP or API serving.
- Watch mode.
- Git hook installation and checkpoint mode.
- Write-capable MCP tools such as graph update tools.
- Automatic code editing.
- Automatic refactoring.
- PR review bot behavior.
- Vector database requirement.
- Embeddings requirement.
- AI or LLM-required graph generation.
- Optional AI enrichment providers.
- Runtime package-registry lookups.
- Telemetry, analytics, or remote crash reporting.
- Multi-repo organization graph.
- Graphify import/export compatibility commands.
- PDF, video, image, or multimodal parsing.
- Deep semantic call graphs.
- Full TypeScript compiler resolution.
- Tree-sitter integration.
- Full framework route extraction.
- Full lockfile dependency graph parsing.
- Full workspace manager implementations.
- Full Make, shell, Docker, CI, or YAML semantic evaluation.
- Secret content scanning.
- Unsafe include-secrets options.
- MCP source-file read tools.
- Formal JSON Schema files for artifacts.
- PyPI publishing and Docker registry publishing.
- License finalization beyond marking it as a pre-release decision.
- Dependabot or dependency update automation.
- Pre-commit hook setup for contributors.

## Further Notes

- The current repository is a minimal Python stub and should be treated as greenfield for RepoLens implementation.
- There are no existing domain docs, ADRs, test fixtures, CI workflows, lint config, typecheck config, package layout, or MCP server code.
- The resolved issue tracker direction is GitHub Issues for the repository remote, with `ready-for-agent` applied to the published PRD issue.
- The PRD issue should be followed by an umbrella v0.1 tracking issue and vertical-slice implementation issues.
- The intended implementation branch is `feature/repolens-v0.1`.
- Implementation should proceed in small verified slices with area-prefixed commits.
- Before implementation, create a separate resolved-decision document and a vertical-slice implementation plan if those docs do not already exist.
- The stray embedding text in the client request is treated as accidental pasted text and does not override the explicit no-embeddings v0.1 policy.
- RepoLens artifacts may contain sensitive repository metadata such as paths, symbol names, comments, command names, dependency names, and hashes. They should be treated as local artifacts and not published blindly.
