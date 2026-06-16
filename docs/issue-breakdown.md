Proposed breakdown: 1 umbrella tracker plus 13 AFK vertical slices. I have not published issues yet.
1. Title: RepoLens MCP v0.1 umbrella tracker 
Type: AFK 
Blocked by: None 
User stories covered: Coordinates 1-76 
This is a tracking issue, not an implementation slice.
2. Title: Installable CLI Scaffold With Missing-Graph Status 
Type: AFK 
Blocked by: None 
User stories covered: 6, 7, 38, 64, 65, 70, 73, 76 
Establishes the repolens package, Typer CLI, Hatchling packaging, pytest/Ruff/mypy checks, JSON/text CLI envelopes, and a read-like status path that reports missing artifacts without mutation.
3. Title: Safe Repository Discovery And Artifact Bootstrap 
Type: AFK 
Blocked by: 2 
User stories covered: 1, 2, 3, 12-21, 64-67 
Adds index traversal that respects repo-root containment, .gitignore, built-in excludes, secret-file skips, binary/media and size caps, non-Git roots, repo-relative paths, .repolens/.gitignore, skip reasons, and sanitized logs.
4. Title: Deterministic Graph Store And Exports 
Type: AFK 
Blocked by: 3 
User stories covered: 47-50, 64, 72, 74, 75 
Creates the SQLite graph store, schema/version metadata, atomic rebuild/export behavior, and deterministic graph.json, graph-lite.json, graph-report.md, graph-index.md, and graph-status.json.
5. Title: Python Structure Indexing End To End 
Type: AFK 
Blocked by: 4 
User stories covered: 22, 23, 28-30, 44, 45 
Indexes Python fixtures through CLI to graph artifacts and reports, including imports, functions, async functions, classes, methods, decorators, inheritance metadata, tagged comments, stdlib/third-party separation, and parse-error handling.
6. Title: JavaScript And TypeScript Structure Indexing End To End 
Type: AFK 
Blocked by: 4 
User stories covered: 22, 24-27, 29, 31 
Indexes JS/TS fixtures through CLI to graph artifacts and reports, including supported extensions, imports/exports, obvious top-level symbols, interfaces, type aliases, package normalization, Node built-ins, and deterministic simple alias resolution.
7. Title: Config, Command, Package, And Entrypoint Indexing 
Type: AFK 
Blocked by: 4 
User stories covered: 29, 31-40, 61 
Extracts shallow facts from project configs, requirements, package manifests, Dockerfiles, Makefiles, task files, GitHub Actions, and pre-commit config, including sanitized candidate commands, package roots, package managers, dependencies, lockfile metadata, and evidence-backed entrypoints.
8. Title: Markdown, Comments, Docs, And Agent Guidance Indexing 
Type: AFK 
Blocked by: 4 
User stories covered: 41-46 
Extracts README metadata, Markdown headings, links, exact path mentions, code-fence metadata without code bodies, tagged comments, agent instruction files, and skill metadata into graph artifacts.
9. Title: Incremental Update And Staleness Classification 
Type: AFK 
Blocked by: 5, 6, 7, 8 
User stories covered: 4-11, 50, 74, 75 
Implements update and richer status, including raw/normalized/graph hashes, Git branch/commit stale signals, config/extractor version invalidation, and change classifications for content-only, structural, dependency, new, deleted, and parse-error changes.
10. Title: Report And Safe Raw Text Search CLI 
Type: AFK 
Blocked by: 4 
User stories covered: 38, 47, 53, 55, 62, 64 
Implements report and CLI search, reading existing artifacts where appropriate and using the same scan safety policy for capped, sanitized, live raw-text results.
11. Title: Structured Graph Query Service 
Type: AFK 
Blocked by: 5, 6, 7, 8 
User stories covered: 51-58, 61-63 
Adds the framework-independent query service for repo summary, graph status, graph report, structured search, node lookup, neighbors, shortest path, and entrypoints with confidence, evidence, limits, stale warnings, and ambiguity handling.
12. Title: Impact Analysis And Reading Order Queries 
Type: AFK 
Blocked by: 11 
User stories covered: 59, 60, 62, 63 
Adds deterministic impact analysis and suggested reading order over the graph, including likely affected files, dependents, tests, docs, configs, risk comments, candidate verification commands, evidence, and caps.
13. Title: Read-Only Stdio MCP Server 
Type: AFK 
Blocked by: 10, 11, 12 
User stories covered: 51-63 
Exposes the resolved v0.1 MCP tools over stdio with read-only behavior, missing-graph responses, stdout discipline, structured success/error envelopes, live status TTL behavior, response caps, and MCP smoke coverage.
14. Title: Docker, Assistant Config, And Release Readiness Docs 
Type: AFK 
Blocked by: 13 
User stories covered: 68-72, 76 
Adds Docker support, host-user mapping examples, native install docs, OpenCode MCP example, README quickstart/security/config/tooling guidance, release smoke checks, and final dogfooding criteria.
   
Questions before I publish:
1. Does this granularity feel right, or are any slices too coarse/fine?
2. Are the dependency relationships correct?
3. Should any slices be merged or split further?
4. Are all slices correctly marked AFK, or should any be HITL?
5. If there is an existing GitHub PRD issue, send its issue number/URL so I can reference it as the parent; otherwise I’ll omit Parent and create the umbrella tracker first.
