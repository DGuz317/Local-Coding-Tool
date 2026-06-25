# RepoLens MCP v0.1 Decisions Archive

Status: archived historical decision summary.

## Product Boundary

- RepoLens v0.1 is a local-first repository intelligence backend for AI coding assistants.
- Core graph generation is deterministic, local, offline-capable, and does not require AI models, embeddings, telemetry, cloud services, or runtime network calls.
- HTTP serving, watch mode, Git hooks, browser UI, AI enrichment, embeddings, Graphify import/export, write-capable MCP tools, and deep semantic call graphs were out of scope.

## Package And CLI

- Project identity: `repolens`.
- Python baseline: `>=3.11`.
- Source layout: `src/repolens`.
- Console script: `repolens = "repolens.cli:app"`.
- CLI framework: Typer.
- v0.1 CLI surface: `index`, `update`, `status`, `report`, `search`, and `mcp`.
- `status` is read-like and must not mutate graph artifacts.
- CLI `search` means safe raw text search; structured graph search is exposed through MCP.

## Artifacts And Storage

- `.repolens` is the standard artifact directory under the analysis root.
- `graph.sqlite` is the authoritative graph store after indexing.
- JSON, Markdown, status, and report artifacts are deterministic exports derived from SQLite.
- Full rebuilds build temporary output and atomically replace artifacts after success.

## Scan Safety

- The provided path is the analysis root; RepoLens must not silently expand to a Git root.
- Paths in artifacts and MCP responses are repo-relative POSIX paths.
- Symlinks must not escape the analysis root.
- Default scan policy honors `.gitignore`, built-in excludes, size caps, binary detection, generated-file hints, and secret path patterns.
- Secret-looking files are skipped by path/name before parsing.
- Include patterns may override ordinary excludes but not containment or secret-file safety.

## Extraction And Graph Model

- Python parsing uses the standard AST.
- JavaScript and TypeScript parsing stays pure Python with bounded line/regex scanning.
- Known config files are parsed shallowly for commands, packages, dependencies, tooling, and entrypoint hints.
- Candidate verification commands are detected and marked as not run.
- Markdown extraction records metadata, headings, links, and code-fence metadata without code bodies.
- Node IDs are deterministic and avoid absolute paths.
- Evidence is structured and compact; it does not include full source snippets by default.
- User-facing confidence is categorical: high, medium, or low.

## MCP And Release

- MCP uses the official Python MCP SDK over stdio.
- MCP v0.1 is read-only and never updates graphs, modifies files, executes commands, or reads whole source files.
- Success responses use a consistent envelope with data, freshness, warnings, limits, and truncation metadata.
- Quality checks are pytest, Ruff check, Ruff format check, and mypy.
