# RepoLens MCP v0.1 Decisions

This document summarizes locked implementation decisions for RepoLens MCP v0.1. The source of truth is the v0.1 PRD; this file is the short operational reference for implementation agents.

## Product Boundary

- RepoLens MCP v0.1 is a local-first repository intelligence backend for AI coding assistants.
- The v0.1 loop is CLI indexing, local `.repolens` artifacts, read-only stdio MCP tools, Docker support, assistant configuration examples, docs, and tests.
- Core graph generation must be deterministic, local, offline-capable, and not require AI models, embeddings, telemetry, cloud services, or runtime network calls.
- HTTP serving, watch mode, Git hooks, browser UI, interactive visualization, AI enrichment, embeddings, Graphify import/export, write-capable MCP tools, and deep semantic call graphs are out of scope.

## Package And CLI

- The project identity is `repolens`; no backward compatibility is needed for the previous stub identity.
- Python baseline is `>=3.11`.
- The package uses a standard `src/repolens` layout.
- The console script is `repolens = "repolens.cli:app"`.
- Typer provides the user-facing CLI.
- CLI output defaults to concise plain text. Machine-readable output uses a JSON envelope where practical.
- The v0.1 CLI surface includes implemented commands only: `index`, `update`, `status`, `report`, `search`, and `mcp`.
- `status` is read-like and must not mutate graph artifacts. Missing artifacts report stale with a recommended action rather than failing by default.
- `report` prints the existing graph report by default. Regeneration from the graph store must be explicit.
- CLI `search` means raw text search. Structured graph search is exposed through MCP.

## Artifacts And Storage

- `.repolens` is the standard artifact directory under the analysis root.
- `.repolens` is local cache by default and should include an internal `.gitignore` instead of modifying the root ignore file.
- RepoLens must never scan `.repolens` itself.
- `graph.sqlite` is the authoritative store after graph storage exists.
- JSON, Markdown, status, and report artifacts are deterministic exports derived from SQLite.
- Full rebuilds build a temporary database and replace it atomically after success.
- Export files are written to temporary files and atomically replaced.
- Artifacts include version, schema, extractor, timestamp, Git, config hash, and scan provenance where available.
- Unsupported schema versions trigger a rebuild in v0.1 rather than migrations.
- Parser, extractor, or effective config changes force reparse or full scan as appropriate.

## Scan Safety

- The provided path is the analysis root. RepoLens must not silently expand to a Git root.
- File discovery works for any existing readable directory and does not require Git.
- Paths in artifacts and MCP responses are repo-relative POSIX-style paths.
- Absolute paths stay internal unless an MCP input absolute path resolves inside the analysis root and is normalized to a repo-relative path.
- Symlinks must never escape the analysis root. Internal symlinks are not traversed in v0.1.
- Default scan policy honors `.gitignore`, built-in excludes, size caps, binary detection, generated-file hints, and secret path patterns.
- Secret-looking files are skipped by path/name before parsing. Content secret scanning is out of scope.
- Secret-like metadata and command values are sanitized before they are written to artifacts or logs.
- Include patterns may override ordinary default excludes but must not bypass containment or secret-file safety in v0.1.
- No unsafe include-secrets option exists in v0.1.

## Language And Config Extraction

- Python parsing uses the standard AST and extracts core symbols, imports, decorators, inheritance metadata, tagged comments, and shallow same-module calls where confidence is high.
- Python syntax errors are nonfatal, remove stale facts for that file, and record parse-error state.
- JavaScript and TypeScript parsing stays pure Python with bounded line/regex scanning.
- Tree-sitter, Node parser dependencies, and full TypeScript compiler resolution are deferred.
- Python stdlib imports and Node built-ins are classified separately from third-party packages.
- External packages include declared dependencies and observed imports.
- Lockfiles are detected but not deeply parsed.
- Known configuration files are parsed for commands, package roots, dependencies, tooling, and entrypoint hints.
- Candidate verification commands are detected and marked as not run. Deploy/publish-like commands are not recommended for automatic execution.
- Markdown parsing extracts headings, README title/intro, code-fence metadata, tagged comments, local links, and exact path mentions where resolvable.
- Full Markdown content, Markdown code block bodies, and routine untagged comment nodes are not copied into graph artifacts by default.

## Graph Model

- Node IDs are deterministic, readable, and path-plus-qualified-name based where possible.
- Line numbers are metadata, not primary identity.
- Repository and directory node IDs avoid absolute paths.
- Edge directions use active source-to-target semantics.
- `IMPORTS` represents raw import evidence.
- `DEPENDS_ON` represents resolved or derived dependency relationships.
- `REFERENCES` represents code/config references.
- `MENTIONS` is reserved for sparse exact prose/comment references.
- `CONFIGURES` links config files to known commands, packages, tools, and entrypoints, not every arbitrary key.
- `ENTRYPOINT_FOR` links an entrypoint file or command to the repository, package, or runtime context it starts.
- Evidence is structured and compact. It does not include full source snippets by default.
- User-facing confidence is categorical: high, medium, or low.

## MCP

- MCP uses the official Python MCP SDK over stdio.
- MCP v0.1 is read-only. It does not update graphs, modify files, execute commands, or read whole source files.
- MCP can start before indexing and should return actionable missing-graph responses.
- Stdio mode must not write logs or progress to stdout.
- Success responses use a consistent envelope with data, freshness, warnings, limits, and truncation metadata.
- Expected errors use structured payloads.
- The v0.1 tools are `repo_summary`, `graph_status`, `get_graph_report`, `search_graph`, `search_text`, `get_node`, `get_neighbors`, `shortest_path`, `impact_analysis`, `suggest_reading_order`, and `list_entrypoints`.

## Testing And Release

- Tests verify external behavior, not implementation details.
- Indexing behavior is tested through CLI commands operating on temporary fixture repositories.
- Query behavior is tested through a framework-independent query service backed by generated graph storage.
- MCP has query-service coverage plus a small stdio protocol smoke test where practical.
- Quality checks are pytest, Ruff check, Ruff format check, and mypy.
- Docker is supported for users who do not want to install Python locally.
- Native install docs prioritize `pipx` or `uv tool`.
- PyPI publishing, Docker registry publishing, and final license/legal decisions are deferred release decisions.
