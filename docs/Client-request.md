# Product Requirement Document: Local Repo Graph MCP Tool

## 1. Product Name

Working name: **RepoLens MCP**

The final product name can change later. For now, this document refers to the product as RepoLens MCP.

## 2. Client Objective

We want to build a local backend tool that analyzes a software repository, generates repo graph artifacts, and exposes that graph through a local MCP server so AI coding assistants can understand the codebase faster.

The tool should reduce the amount of repeated `grep`, `glob`, and file-reading that AI assistants perform when working inside a repository.

The tool should let an assistant quickly answer:

* What are the main entrypoints?
* What files are important?
* What modules exist?
* What functions/classes/symbols are defined?
* What files import or depend on other files?
* What tests are likely related to a source file?
* What files should be read first for a given coding task?
* What impact might a change have?
* Is the generated graph fresh or stale?

## 3. Problem Statement

AI coding assistants often waste time and tokens rediscovering a repository structure on every session.

Common behavior today:

1. The assistant lists files.
2. The assistant searches with `grep` or `glob`.
3. The assistant opens many source files.
4. The assistant infers architecture from raw code.
5. The assistant may still miss important entrypoints, tests, configs, or related files.

This is inefficient and unreliable for large codebases.

We want the tool to generate a compact, queryable repo map ahead of time so the assistant can start with structured context instead of raw exploration.

## 4. Target Users

### Primary users

* Developers using OpenCode, Codex, Claude Code, Cursor, or other MCP-compatible coding assistants.
* Teams that want AI assistants to understand their codebase faster.
* Developers working with medium or large repositories where repeated repo scanning is expensive.

### Secondary users

* AI agent builders.
* Developer tooling teams.
* Maintainers who want repo architecture reports.

## 5. Product Summary

RepoLens MCP is a local-first repo intelligence backend.

It should:

1. Scan a local repository.
2. Build a graph of files, symbols, imports, dependencies, configs, tests, and entrypoints.
3. Save graph artifacts into a local `.repolens/` directory.
4. Expose read-only graph query tools through a local MCP server.
5. Allow coding assistants to query the graph before opening source files.

The product should work locally through either:

```bash
git clone <repo>
```

or:

```bash
docker run ...
```

The first version does not need cloud sync, user accounts, hosted storage, or a web dashboard.

## 6. Core Product Principle

The assistant should not rediscover the repository from scratch every time.

Expected flow:

```text
User repo
  -> RepoLens indexer
  -> .repolens graph artifacts
  -> local MCP server
  -> AI assistant queries graph
  -> AI opens only targeted source files
```

## 7. MVP Scope

The MVP should generate local repo context artifacts and expose them through MCP.

### Required MVP features

* Local CLI.
* Local indexing command.
* Local MCP server command.
* Docker support.
* Graph artifact generation.
* Basic language support.
* File change detection.
* Graph staleness detection.
* Read-only MCP query tools.
* OpenCode configuration example.
* Clear README with install and usage instructions.

### Initial language support

The first version should support:

* Python
* JavaScript
* TypeScript
* Markdown
* JSON
* YAML
* TOML

Other languages can be added later.

## 8. Expected CLI Commands

The product should provide these commands:

```bash
repolens index <repo-path>
```

Indexes a repository and generates `.repolens/` artifacts.

```bash
repolens update <repo-path>
```

Updates an existing graph using incremental file change detection.

```bash
repolens status <repo-path>
```

Shows whether the graph is fresh or stale.

```bash
repolens report <repo-path>
```

Regenerates or prints the graph report.

```bash
repolens mcp <repo-path>
```

Starts the local MCP server using stdio transport.

```bash
repolens serve <repo-path> --host 127.0.0.1 --port 8787
```

Optional later command for HTTP transport.

## 9. Generated Artifacts

The tool must generate a `.repolens/` directory in the target repository.

Required files:

```text
.repolens/
  graph.sqlite
  graph.json
  graph-lite.json
  graph-report.md
  graph-index.md
  graph-status.json
  index.log
```

### 9.1 `graph.sqlite`

Purpose: local source of truth.

Used by:

* MCP server
* query engine
* incremental update logic
* report generator

The AI assistant does not need to read this directly.

### 9.2 `graph.json`

Purpose: full machine-readable graph export.

It should include:

* repository metadata
* files
* directories
* symbols
* functions
* classes
* methods
* imports
* packages
* configs
* tests
* nodes
* edges
* entrypoints
* hashes
* line ranges
* evidence

It should not include full source code unless explicitly configured.

### 9.3 `graph-lite.json`

Purpose: compact AI-first context file.

This should be small enough for an AI assistant to read early in a session.

It should include:

* repo summary
* detected languages
* entrypoints
* important files
* major modules
* safe commands
* read-first recommendations
* test/lint/build availability
* graph freshness summary

### 9.4 `graph-report.md`

Purpose: human-readable and AI-readable repo report.

It should summarize:

* project purpose
* entrypoints
* commands
* major modules
* important files
* key flows
* test relationships
* architectural hotspots
* agent reading guide
* stale graph status

The report should be concise. It should be a map, not a full source-code mirror.

### 9.5 `graph-index.md`

Purpose: readable index of important files and symbols.

It should include tables for:

* files
* symbols
* modules
* entrypoints
* tests
* configs

### 9.6 `graph-status.json`

Purpose: freshness and change tracking.

It should include:

* indexed timestamp
* git branch
* git commit if available
* changed files
* deleted files
* new files
* content-only changes
* structural changes
* dependency changes
* whether reindexing is required

### 9.7 `index.log`

Purpose: debugging and observability.

It should include:

* indexing start/end
* skipped files
* parser errors
* unsupported files
* performance timings

## 10. Graph Data Model

### Node types

The graph should support these node types:

* `Repository`
* `Directory`
* `File`
* `Module`
* `Symbol`
* `Function`
* `Class`
* `Method`
* `Import`
* `Package`
* `ConfigFile`
* `TestFile`
* `Command`
* `Skill`
* `MarkdownSection`

### Edge types

The graph should support these relationship types:

* `CONTAINS`
* `DEFINES`
* `IMPORTS`
* `CALLS`
* `REFERENCES`
* `TESTS`
* `CONFIGURES`
* `DEPENDS_ON`
* `DOCUMENTS`
* `MENTIONS`
* `ENTRYPOINT_FOR`

## 11. Change Detection Requirements

The tool must detect file changes accurately.

Each indexed file should track:

* `raw_hash`
* `normalized_hash`
* `graph_hash`
* file size
* modified timestamp
* indexed timestamp
* language
* parser status

### Change categories

The system should classify file changes as:

* `NO_CHANGE`
* `CONTENT_ONLY_CHANGE`
* `STRUCTURAL_CHANGE`
* `DEPENDENCY_CHANGE`
* `NEW_FILE`
* `DELETED_FILE`
* `PARSE_ERROR`

### Blank-line requirement

If a user adds only a blank line to a file:

* the tool must detect that the raw file changed
* the tool should update line ranges if needed
* the tool should not mark the dependency graph as meaningfully changed unless symbols/imports/calls changed

Expected behavior:

```text
blank line added
  -> raw_hash changed
  -> normalized_hash may remain unchanged
  -> graph_hash usually unchanged
  -> graph-status.json reports content-only change
```

## 12. MCP Server Requirements

The product must expose a local MCP server.

The first version should support stdio transport.

Command:

```bash
repolens mcp <repo-path>
```

The MCP server should load existing `.repolens/` artifacts instead of rescanning the repo on every request.

### Required MCP tools

#### `repo_summary`

Returns high-level repo summary.

Should include:

* languages
* entrypoints
* major modules
* important files
* available commands
* test/lint/typecheck status

#### `graph_status`

Returns graph freshness information.

Should include:

* indexed timestamp
* stale status
* changed files
* new files
* deleted files
* whether reindexing is recommended

#### `get_graph_report`

Returns the generated `graph-report.md`.

#### `search_graph`

Searches files, symbols, modules, routes, configs, commands, and concepts.

Input:

```json
{
  "query": "auth login"
}
```

#### `get_node`

Returns one graph node by ID or search query.

Input:

```json
{
  "id": "symbol:src/auth/login.py:authenticate_user"
}
```

#### `get_neighbors`

Returns nearby graph relationships around a file, symbol, or module.

Input:

```json
{
  "node_id": "file:src/auth/login.py",
  "depth": 1
}
```

#### `shortest_path`

Finds the graph path between two nodes or concepts.

Input:

```json
{
  "from": "login route",
  "to": "user database"
}
```

#### `impact_analysis`

Given a file or symbol, returns likely affected files, callers, imports, and tests.

Input:

```json
{
  "target": "src/auth/login.py"
}
```full semantic embeddings- full semantic embeddingsScan a local repository

#### `suggest_reading_order`

Given a task, returns the smallest set of files the assistant should inspect first.

Input:

```json
{
  "task": "Add validation to login flow"
}
```

#### `list_entrypoints`

Returns detected app entrypoints, CLIs, routes, workers, scripts, or config-defined commands.

## 13. AI Assistant Usage Requirement

The generated artifacts should be optimized for AI assistant usage.

The recommended assistant behavior should be:

1. Read `graph-report.md`.
2. Read `graph-lite.json`.
3. Call `suggest_reading_order` for the user’s task.
4. Call `impact_analysis` before editing.
5. Open only the source files required for the task.
6. Run focused checks after editing.

The assistant should not begin by blindly scanning the whole repository unless the graph is missing or stale.

## 14. Docker Requirements

The product must be runnable through Docker.

### Index command

```bash
docker run --rm -it \
  -v "$PWD:/workspace" \
  repolens:latest \
  index /workspace
```

### MCP command

```bash
docker run --rm -i \
  -v "$PWD:/workspace" \
  repolens:latest \
  mcp /workspace
```

The Docker image should not require network access at runtime for normal indexing.

## 15. OpenCode Integration Requirement

The product should provide an example `opencode.jsonc` configuration.

Example:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "repolens": {
      "type": "local",
      "command": [
        "docker",
        "run",
        "--rm",
        "-i",
        "-v",
        "$PWD:/workspace",
        "repolens:latest",
        "mcp",
        "/workspace"
      ],
      "enabled": true
    }
  }
}
```

The product should also document a non-Docker setup.

## 16. Security Requirements

The tool must be safe by default.

Required security behavior:

* read-only MCP tools in v0.1
* no arbitrary shell execution
* no code modification in v0.1
* no network calls during normal indexing
* repo-root path containment
* skip `.git`, `node_modules`, `.venv`, `dist`, `build`, cache folders, and generated folders by default
* avoid reading secrets files by default
* apply max file size limits
* apply max output size limits
* apply parser timeouts
* bind HTTP mode to `127.0.0.1` by default
* require explicit configuration before exposing HTTP outside localhost

## 17. Non-Functional Requirements

### Performance

The tool should be usable on small and medium repositories.

Initial target:

* small repo: complete indexing in under 10 seconds
* medium repo: complete indexing in under 2 minutes
* repeated indexing should be faster through incremental updates

### Reliability

The indexer should continue even if some files fail to parse.

Parser errors should be recorded in `index.log` and `graph-status.json`.

### Portability

The tool should work on:

* macOS
* Linux
* Windows through Docker or native Python if possible

### Local-first

No cloud dependency is allowed for core functionality.

### Deterministic output

The first version should use deterministic parsing and static analysis. LLM-based summarization can be optional later but must not be required for the core graph.

## 18. Out of Scope for v0.1

Do not build these in the first version:

* hosted cloud dashboard
* user accounts
* team permissions
* browser UI
* automatic code editing
* automatic refactoring
* PR review bot
* vector database requirement
* embeddings requirement
* multi-repo organization graph
* PDF/video/image parsing
* LLM-required graph generation
* deep semantic call graph for every language

## 19. Recommended Technical Direction

Suggested stack:

* Python for CLI and backend
* Typer for CLI
* Python MCP SDK for MCP server
* SQLite for graph storage
* JSON export for portability
* Tree-sitter where needed
* Python `ast` module for Python parsing
* Docker for distribution
* pytest for tests
* ruff for lint/format
* pyright or mypy for type checking

This stack can change if the implementation team has a better reason, but the product must remain local-first and Docker-friendly.

## 20. Development Milestones

### Milestone 1: Project scaffold

Deliverables:

* CLI package
* Dockerfile
* README
* basic config
* test setup
* empty MCP server

Acceptance criteria:

* `repolens --help` works
* `repolens mcp --help` works
* Docker image builds

### Milestone 2: File discovery and hashing

Deliverables:

* repo scanner
* ignore handling
* file metadata tracking
* raw hash, normalized hash, graph hash fields

Acceptance criteria:

* tool can scan a repo
* skipped files are reported
* blank-line changes are detected as content changes

### Milestone 3: Graph store

Deliverables:

* SQLite schema
* node table
* edge table
* file table
* basic graph export

Acceptance criteria:

* `graph.sqlite` is created
* `graph.json` is created
* files appear as graph nodes

### Milestone 4: Language parsers

Deliverables:

* Python parser
* TypeScript/JavaScript import parser
* Markdown parser
* config parser

Acceptance criteria:

* functions/classes/imports are extracted for Python
* imports are extracted for JS/TS
* headings are extracted for Markdown
* package/config files are identified

### Milestone 5: Report generation

Deliverables:

* `graph-lite.json`
* `graph-report.md`
* `graph-index.md`
* `graph-status.json`

Acceptance criteria:

* generated report summarizes repo entrypoints, commands, files, and modules
* AI assistant can read report without opening many files

### Milestone 6: MCP tools

Deliverables:

* `repo_summary`
* `graph_status`
* `get_graph_report`
* `search_graph`
* `get_node`
* `get_neighbors`
* `shortest_path`
* `impact_analysis`
* `suggest_reading_order`
* `list_entrypoints`

Acceptance criteria:

* OpenCode or another MCP client can connect to the local server
* tools return structured JSON
* tools do not modify files

### Milestone 7: Docker distribution

Deliverables:

* Docker image
* usage examples
* OpenCode config example

Acceptance criteria:

* user can run indexing through Docker
* user can run MCP through Docker
* no local Python install required for Docker usage

### Milestone 8: Incremental indexing

Deliverables:

* changed file detection
* deleted file detection
* new file detection
* graph update logic

Acceptance criteria:

* unchanged files are skipped
* content-only changes are detected
* structural changes update graph nodes and edges
* second run is faster than first run

## 21. Success Criteria

The product is successful when a user can run:

```bash
repolens index /workspace
```

and receive:

```text
/workspace/.repolens/graph.sqlite
/workspace/.repolens/graph.json
/workspace/.repolens/graph-lite.json
/workspace/.repolens/graph-report.md
/workspace/.repolens/graph-index.md
/workspace/.repolens/graph-status.json
```

Then run:

```bash
repolens mcp /workspace
```

and allow an AI coding assistant to answer repo questions without scanning the whole codebase first.

## 22. Example Assistant Prompt

After this PRD is accepted, the implementation assistant should be prompted with:

```text
Use this PRD as the source of truth.

Build the product in vertical slices. Start with the smallest working local CLI that can scan a repository and generate .repolens/graph-status.json.

Do not build cloud features, UI, or code-editing tools.

Use TDD where practical. After each slice, run the smallest relevant verification command and explain what changed, why it changed, and how it affects the flow.
```

## 23. First Implementation Slice

The first implementation slice should be:

```text
Create a CLI command: repolens index <repo-path>
```

It should:

1. validate the repo path
2. create `.repolens/`
3. scan files while respecting basic ignore rules
4. compute `raw_hash`
5. write `graph-status.json`
6. write `index.log`

This slice does not need full AST parsing yet.

Acceptance criteria:

* command runs successfully on a small repo
* `.repolens/graph-status.json` exists
* blank-line file changes are detected on the next run
* skipped directories are listed in the log

## 24. Graph Freshness and Update Timing

The product must support multiple graph update modes.

### 24.1 Manual update mode

The default update command should be:

```bash
repolens update <repo-path>
```

This command updates graph artifacts using incremental file change detection.

### 24.2 Watch mode

The product should support watch mode:

```bash
repolens watch <repo-path>
```

Watch mode should monitor repository file changes and update graph freshness data immediately.

Expected behavior after a code edit:

1. update `graph-status.json` immediately
2. debounce rapid file events
3. update `graph.sqlite` and `graph.json`
4. regenerate `graph-lite.json` if important structure changed
5. regenerate `graph-report.md` only when needed or on checkpoint

### 24.3 Git checkpoint mode

The product should support optional Git hooks:

```bash
repolens hook install <repo-path>
repolens hook uninstall <repo-path>
repolens hook status <repo-path>
```

Supported hooks:

* `post-commit`
* `post-checkout`
* optional `pre-commit`

Checkpoint mode should create a stable graph state tied to Git commits and branch checkouts.

### 24.4 Recommended assistant behavior

After an AI assistant edits code, it should call:

```bash
repolens update <repo-path>
```

or use the MCP tool:

```text
update_graph
```

The assistant should check graph freshness before making follow-up architecture decisions.

## 25. Comment and Annotation Parsing

The product must parse comments and annotations.

For Python, the tool should detect simple comments such as:

```python
# TODO: remove fallback login
# RISK: this bypasses validation
# NOTE: legacy behavior
# SECURITY: check permissions here
```

The parser should classify common comment tags:

* `TODO`
* `FIXME`
* `HACK`
* `NOTE`
* `RISK`
* `SECURITY`
* `WARNING`
* `DEPRECATED`
* `PERF`
* `QUESTION`

Comments should be stored as graph nodes or file annotations.

Example node:

```json
{
  "id": "comment:src/auth/login.py:42",
  "kind": "Comment",
  "tag": "RISK",
  "path": "src/auth/login.py",
  "line": 42,
  "text": "this bypasses validation",
  "attachedTo": "symbol:src/auth/login.py:authenticate_user"
}
```

The product should also detect comments without tags, but tagged comments should receive higher priority in reports and search results.

## 26. Whitespace and Blank-Line Detection

The product must detect blank-line and whitespace-only changes.

Each file should track:

* `raw_hash`
* `normalized_hash`
* `graph_hash`

Expected behavior for a blank-line-only change:

```text
raw_hash changed
normalized_hash may remain unchanged
graph_hash usually unchanged
change_type = CONTENT_ONLY_CHANGE
```

The product should update line ranges if the blank line changes symbol positions.

Whitespace-only changes should not be reported as dependency or structural graph changes unless symbols, imports, calls, or graph edges changed.

## 27. Text Search Requirement

The product must provide a keyword search command.

Required CLI:

```bash
repolens search <repo-path> "<keyword>"
```

Example:

```bash
repolens search . "TODO"
```

Expected output:

```text
src/auth/login.py:42:# TODO: remove fallback login
src/billing/checkout.py:88:# TODO: handle failed payment retry
docs/architecture.md:12:TODO list before launch
```

The product should also expose this through MCP.

Required MCP tool:

```text
search_text
```

Purpose:

Search raw file contents, comments, strings, markdown, and config files.

This is different from:

```text
search_graph
```

`search_graph` searches structured graph data such as symbols, modules, files, relationships, summaries, and tags.

## 28. Interactive Visualization Requirement

The product should eventually provide an interactive graph visualization.

This is not required for v0.1.

The visualization should allow users to interact with nodes.

Required future interactions:

* click a file node to show symbols defined in the file
* click a class node to expand methods
* click a function node to show callers and callees
* click an import node to show dependency direction
* click a test node to show covered source files
* click a comment or risk node to jump to source line
* filter by node type
* filter by edge type
* search within graph
* open source location from a node

Example class interaction:

```text
Class: UserService
  expands to:
    - create_user()
    - get_user()
    - delete_user()

  related nodes:
    - src/db/users.py
    - src/routes/users.py
    - tests/test_users.py
```

Visualization should read from `graph.json` or a dedicated visualization export.

## 29. AI Model Usage Policy

The product must not require an AI model for core graph generation.

The v0.1 graph must be generated through deterministic local analysis:

* file scanning
* hashing
* Python AST parsing
* Tree-sitter parsing where useful
* import parsing
* config parsing
* markdown parsing
* comment parsing
* SQLite graph storage

AI or LLM-based enrichment can be added later as an optional feature.

Optional future command:

```bash
repolens enrich <repo-path> --provider <provider>
```

Optional enrichment may generate:

* module summaries
* feature summaries
* architectural intent summaries
* risk summaries
* documentation summaries

The product must still work when no AI provider is configured.

## 30. Worker Model

The product should use deterministic parser workers in v0.1.

Examples:

* `PythonParser`
* `TypeScriptParser`
* `JavaScriptParser`
* `MarkdownParser`
* `ConfigParser`
* `CommentParser`

These workers are not AI agents.

Future versions may add optional AI enrichment workers, but they must not be required for indexing.

## 31. Graphify Compatibility Strategy

This product should be separate from Graphify, but compatible with Graphify-style workflows where practical.

The MVP should not depend on Graphify.

Recommended compatibility features for future versions:

```bash
repolens export graphify <repo-path>
repolens import graphify-out/graph.json
repolens mcp <repo-path> --graph graphify-out/graph.json
```

The product should keep its core focus:

```text
local deterministic repo graph
AI-first context artifacts
MCP query layer
fast incremental updates
Docker-friendly installation
```

Graphify-style multimodal and LLM-enriched graph generation can be considered later, but should not block the core local-first product.
