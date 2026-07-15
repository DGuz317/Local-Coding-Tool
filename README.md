# RepoLens MCP

RepoLens helps an AI coding assistant understand a repository before it starts opening files or editing code.

Think of it as a local map of your codebase:

- It scans a repository on your machine.
- It writes a generated graph under `.repolens/`.
- It lets assistants ask read-only questions about files, symbols, tests, docs, configs, and relationships.
- It can return a bounded **Assistant Preflight** so an assistant knows what to read first.

RepoLens is local-first. Normal indexing and MCP usage do not require AI models, embeddings, telemetry, hosted services, a browser UI, or runtime network calls.

## Current Release

Current version: **v0.7.0**.

v0.7.0 adds the Python Semantic Analysis Prototype: experimental, source-free function-level control-flow and lexical binding metadata stored separately from the stable graph. Release notes live in `docs/releases/v0.7.0.md`.

v0.7 Python semantic facts are experimental, source-free metadata stored separately from the stable graph. They are candidate metadata for inspection and evaluation only; they do not change the stable graph contract, Canonical Graph Hash, default Context Pack IDs, stable graph validation, default Assistant Preflight output, or default MCP output.

## What Problem Does This Solve?

AI coding assistants often waste context by reading too many files too early.

RepoLens gives the assistant a safer and cheaper first step:

1. Build a graph from the repository source, docs, configs, tests, and commands.
2. Ask RepoLens for task-scoped orientation instead of starting with broad grep or random file reads.
3. Ask for an Assistant Preflight before broad file reads, then open only the most relevant source files before editing.

RepoLens is meant to replace broad exploratory codebase scanning, not the final targeted source review needed before making a safe edit.

## Install And Connect

Build and install RepoLens as a local tool, then register the installed command with your MCP
client. No project settings or separate indexing command are required:

```bash
uv build --out-dir /tmp/repolens-dist --clear
uv tool install --force /tmp/repolens-dist/*.whl
```

Copy this installed-command shape into a supported MCP client, replacing the repository path:

```json
{
  "mcpServers": {
    "repolens": {
      "command": "repolens",
      "args": ["mcp", "/absolute/path/to/repo"]
    }
  }
}
```

OpenCode uses the equivalent local command array:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "repolens": {
      "type": "local",
      "command": ["repolens", "mcp", "/absolute/path/to/repo"],
      "enabled": true
    }
  }
}
```

Ask the assistant to call `assistant_preflight` with its task before broad file reads. On the
first call RepoLens discovers the repository root and creates the missing graph; later calls
refresh stale graph state. This local first-use path does not contact a network or run the
repository's package managers, compilers, bundlers, or frameworks.

## Requirements

You need:

- Python 3.11 or newer.
- `uv` for local development commands.

This project uses `uv`, so prefer `uv run ...` instead of assuming your global `python`, `pytest`, or `repolens` command points at the right environment.

## First Walkthrough

### 1. Install The Local Environment

```bash
uv sync
```

### 2. Check The CLI

```bash
uv run repolens --help
```

### 3. Index A Repository

To index the current repository:

```bash
uv run repolens index .
```

To index another repository:

```bash
uv run repolens index /path/to/repo
```

This creates generated files under `/path/to/repo/.repolens/`.

### 4. Check Whether The Graph Is Ready

```bash
uv run repolens status /path/to/repo
```

If RepoLens says the graph is stale or missing, run `index` again:

```bash
uv run repolens index /path/to/repo
```

### 5. Ask For Assistant Preflight

```bash
uv run repolens preflight /path/to/repo "Fix the auth timeout bug"
```

Assistant Preflight is the recommended first assistant call before broad file reads. It returns a bounded orientation result that can include things like:

- first files to read;
- likely tests;
- supporting docs or configs;
- risk signals;
- candidate verification commands that were found but not run;
- confidence, freshness, warning, and truncation metadata.

It intentionally does not include full source files or source snippets.

## Common Commands

```bash
uv run repolens index /path/to/repo
uv run repolens update /path/to/repo
uv run repolens status /path/to/repo
uv run repolens report /path/to/repo
uv run repolens search /path/to/repo "query text"
uv run repolens context /path/to/repo "Describe your task"
uv run repolens preflight /path/to/repo "Describe your task"
uv run repolens create-ai-proposal /path/to/repo context_pack_summary "Describe your task" --enable-ai --provider test --model context-pack-summary-v1 --json
uv run repolens audit-artifacts /path/to/repo
uv run repolens semantic-inspect path/to/file.py --repo-path /path/to/repo --json
uv run repolens semantic-inspect path/to/file.py --repo-path /path/to/repo --from-source --json
uv run repolens evaluate-semantics --json
uv run repolens mcp /path/to/repo

Command meanings:

- `index`: rebuild RepoLens graph artifacts from scratch.
- `update`: update artifacts from detected local changes, or initialize if missing.
- `status`: check graph freshness without creating `.repolens/`.
- `report`: print the generated Markdown graph report.
- `search`: search scanner-approved live text with capped previews.
- `context`: return a task-scoped Context Pack.
- `preflight`: return the Assistant Preflight contract for a task, including graph freshness, first-read files, likely tests, candidate commands, focus hints, warnings, and budget metadata.
- `create-ai-proposal`: explicitly request an optional v0.8 AI Proposal from bounded RepoLens metadata; AI is disabled by default and the current implementation supports only the local deterministic `test` provider.
- `audit-artifacts`: locally check generated `.repolens/` artifacts and representative assistant-facing output for disclosure and safety invariants. Pass `--include-ai-proposals` to audit explicitly saved proposal artifacts.
- `repolens semantic-inspect` reads indexed semantic artifacts by default. When indexed semantic artifacts are missing, stale, or incompatible, `semantic-inspect` reports artifact status instead of silently parsing live source.
- `semantic-inspect --from-source` is an explicit, non-persistent debug mode. It does not persist artifacts, and output is labeled debug metadata rather than indexed repository state.
- `evaluate-semantics`: run deterministic Python semantic fixture evaluation for control-flow, lexical binding, warning, no-disclosure, stable identity, and artifact-audit evidence.
- `mcp`: start the read-only stdio MCP server for an assistant.

For JavaScript and TypeScript repositories, v0.6 uses the Tree-sitter JS/TS parser backend by default when the parser and grammar packages are available. If they are unavailable, RepoLens falls back to the legacy bounded scanner and emits parser-backend warnings instead of pretending parser-backed facts exist.

v0.6 metadata remains orientation-only:

- Call Chain Facts are source-free structural facts with names, receiver shape, and bounded line ranges. They are not runtime reachability proof, deep semantic call graphs, or data-flow analysis.
- Framework Route Hints are deterministic hints from local file/config/parser evidence. The first fixture covers Next.js App Router shapes, but hints are not framework emulation or runtime route proof.
- Resolver outcomes preserve uncertainty with unresolved statuses, candidates, Relationship Candidates, and Graph Quality Warnings when local evidence is incomplete.


For Python repositories, v0.7 semantic facts are experimental, source-free metadata stored separately from stable graph artifacts:

- Control-flow facts describe function-level entry, branch, loop, return, raise, exit, unsupported, and uncertain paths. They are not runtime reachability proof, data-flow analysis, taint analysis, or type inference.
- Lexical binding facts describe local definitions, parameters, imports, assignments, references, unresolved names, free-variable candidates, shadowing, `global`, and `nonlocal` declarations where deterministic AST evidence exists. They do not prove runtime values or fully resolve dynamic Python behavior.
- Indexed `semantic-inspect` reads `.repolens/semantic.sqlite` by default and reports missing, stale, or unsupported artifacts with freshness metadata.
- `--from-source` is explicit, non-persistent debug mode. It does not update `graph.sqlite`, `.repolens/semantic.sqlite`, Canonical Graph Hash inputs, default Context Pack IDs, or default MCP output.
- Semantic facts and debug/evaluation exports must not include source snippets, raw condition text, function signatures, raw expression text, raw values, code bodies, raw comments, raw docstrings, absolute host paths, or AI prose summaries.

There is also a developer-oriented `benchmark-update` command for update-speed evidence.

For machine-readable output, commands that support it accept `--json`:

```bash
uv run repolens preflight /path/to/repo "Fix the auth timeout bug" --json
```

## Using RepoLens With An Assistant

RepoLens is most useful when an MCP client starts it for an assistant.

The basic flow is:

1. Configure your MCP client to run `repolens mcp /absolute/path/to/repo`.
2. Tell the assistant to call `assistant_preflight` before broad file exploration.
3. Let that first tool call discover the repository and initialize or refresh its graph.

MCP command shape:

```bash
uv run repolens mcp /absolute/path/to/repo
```

Important: `repolens mcp` is not an interactive terminal command. It waits for JSON-RPC messages from an MCP client. If you run it manually, it should appear to sit there silently.

## Assistant Prompt Guidance

Recommended assistant prompt:

```text
Use RepoLens MCP for this repository before broad file exploration. Start each task by calling assistant_preflight with the task description. Treat the response as orientation metadata, not source code. Read the returned first-read files before editing. Candidate commands are found but not run.
```

For more assistant setup details, see:

- `docs/assistant-usage-guide.md`
- `docs/ai-proposals.md` for v0.8 provider setup, metadata input, persistence, trust boundaries, and proposal limitations
- `docs/mcp-tool-examples.md`
- `docs/opencode-mcp.example.jsonc`

## OpenCode Example

For local contributor development from this repository, create an OpenCode config like this and replace the paths:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "repolens": {
      "type": "local",
      "command": [
        "uv",
        "run",
        "repolens",
        "mcp",
        "/absolute/path/to/repo"
      ],
      "cwd": "/absolute/path/to/repolens-checkout",
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

Use absolute paths. `cwd` should point at this RepoLens checkout when using `uv run`. The MCP argument should point at the repository you want RepoLens to inspect.

## Claude Desktop Example

Claude Desktop uses an `mcpServers` object. For local contributor development from this repository, use absolute paths and point `cwd` at the RepoLens checkout:

```json
{
  "mcpServers": {
    "repolens": {
      "command": "uv",
      "args": ["run", "repolens", "mcp", "/absolute/path/to/repo"],
      "cwd": "/absolute/path/to/repolens-checkout"
    }
  }
}
```

After connecting, ask Claude to call `assistant_preflight` before broad file reads.

## Cursor-Style MCP Example

Cursor-style MCP config also uses an `mcpServers` object. Keep project-specific config local unless you intentionally want to share it:

```json
{
  "mcpServers": {
    "repolens": {
      "command": "uv",
      "args": ["run", "repolens", "mcp", "/absolute/path/to/repo"],
      "cwd": "/absolute/path/to/repolens-checkout"
    }
  }
}
```

Use the same assistant instruction: call `assistant_preflight` for the task before broad file exploration, then read the returned files directly before editing.

If RepoLens is installed as a normal tool, the command can be shorter:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "repolens": {
      "type": "local",
      "command": ["repolens", "mcp", "/absolute/path/to/repo"],
      "cwd": "/absolute/path/to/repo",
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

## Native Install

Package publishing is deferred, so install from a local checkout or built wheel.

Install from a local checkout:

```bash
uv tool install /path/to/repolens
repolens --help
```

Local PyPI-readiness smoke without publishing:

```bash
uv build --out-dir /tmp/repolens-dist --clear
uv tool install --force /tmp/repolens-dist/*.whl
repolens --help
repolens preflight /absolute/path/to/repo "Check install readiness" --json
uv tool uninstall repolens
```

This only builds and installs a local wheel. It does not upload to PyPI.

If you prefer `pipx`:

```bash
pipx install /path/to/repolens
repolens --help
```

Build and install a wheel for smoke testing:

```bash
uv build
uv tool install --force dist/*.whl
repolens --help
```

## Docker Usage

Build the local image:

```bash
docker build -t repolens:latest .
```

Index the current repository without runtime network access:

```bash
docker run --rm \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  repolens:latest \
  index /workspace
```

Run a status check:

```bash
docker run --rm \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  repolens:latest \
  status /workspace
```

Run an Assistant Preflight smoke through Docker:

```bash
docker run --rm \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  repolens:latest \
  preflight /workspace "Check Docker install readiness" --json
```

Start the MCP server through Docker:

```bash
docker run --rm -i \
  --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  repolens:latest \
  mcp /workspace
```

The `--user "$(id -u):$(id -g)"` part helps avoid root-owned `.repolens/` files on your host machine.

## Artifact Privacy

### What RepoLens Is Allowed To Do

RepoLens is designed to be safe and read-oriented:

- It stays inside the repository path you give it.
- It skips `.repolens/`, dependency folders, virtual environments, caches, build outputs, and common generated paths.
- It honors `.gitignore` during file discovery.
- It skips secret-looking files by path or name before parsing.
- It sanitizes secret-like command and metadata values before writing artifacts.
- It skips oversized, binary, media, archive, and unsafe symlink targets.
- It may detect candidate verification commands, but it does not run them.
- Its MCP tools are read-only.
- It does not expose full source files through MCP tools.

Content secret scanning is limited and conservative. Do not intentionally put secrets in source files. Treat `.repolens/` as private local repository metadata.

More detail lives in `docs/security-and-artifact-privacy.md`.

## Generated Artifacts

RepoLens writes generated output under `.repolens/` in the repository being analyzed.

That directory can contain metadata such as:

- file paths;
- symbols;
- dependencies;
- commands;
- Markdown headings;
- tagged comments;
- graph relationships;
- capped reports and indexes.

Do not commit, publish, upload, or share `.repolens/` unless you have reviewed it and are comfortable exposing repository metadata.

Default Markdown artifacts such as `.repolens/graph-index.md` are bounded navigation views, not full graph dumps. SQLite remains the complete graph source of truth. The artifact budget contract and truncation metadata rules live in `docs/artifact-budget-contract.md`.

When `graph-index.md` omits rows, inspect `.repolens/graph-status.json` for `exports.graph_index.truncated` and per-section `shown`, `total`, and `reason` values. Retrieve omitted graph facts with bounded graph metadata queries instead of opening or generating huge Markdown:

```bash
uv run repolens search-graph . auth --kind symbol --limit 20 --json
uv run repolens search-graph . login --kind file --limit 20 --json
uv run repolens search-graph . test --kind command --limit 20 --json
```

If deeper inspection is still needed, query `.repolens/graph.sqlite` or inspect `.repolens/graph.json` with targeted filters. Full or sharded Markdown index export is not enabled by default; if a future release adds it, that export must preserve the same no whole-source disclosure boundary and should not mirror full source files into generated Markdown.

## Setup Diagnostics

Before connecting an assistant, run these local checks:

```bash
uv run repolens --help
uv run repolens index /absolute/path/to/repo
uv run repolens status /absolute/path/to/repo
uv run repolens preflight /absolute/path/to/repo "Check setup" --json
```

Expected result: the graph exists, freshness is reported, preflight returns bounded metadata, and candidate verification commands remain `run: false`. If any step fails, fix local installation or graph freshness before relying on MCP output.

## Troubleshooting

If RepoLens says artifacts are missing:

```bash
uv run repolens index /path/to/repo
```

If RepoLens says artifacts are stale after file changes:

```bash
uv run repolens update /path/to/repo
```

If you want to force a clean rebuild:

```bash
uv run repolens index /path/to/repo
```

If `repolens mcp` appears frozen, that is usually expected. It is waiting for an MCP client.

More help:

- `docs/troubleshooting.md`
- `docs/known-limitations.md`

## Developer Checks

Run the normal verification gate before submitting changes:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
```

Run Context Pack evaluation fixtures:

```bash
uv run repolens evaluate-context
```

Run update benchmark evidence:

```bash
uv run repolens benchmark-update
```

Release-prep guidance lives in:

- `docs/release-readiness.md`
- `docs/release-checklist.md`

## Human Release Checkpoint

Before release, run the full verification gate, review generated artifact behavior on representative repositories, and confirm release-readiness evidence in `docs/release-readiness.md`.

## Roadmap And Non-Goals

RepoLens v0.6 focuses on improving JS/TS parser and resolver evidence for that deterministic preflight workflow while preserving source-safety and uncertainty.

RepoLens v0.7 focuses on the Python Semantic Analysis Prototype: source-free function-level CFG and lexical binding facts in an experimental layer that remains separate from the stable graph contract.

Current focus:

- local CLI indexing, update, status, report, search, context, semantic inspection, semantic evaluation, and read-only MCP serving;
- deterministic `.repolens/` graph artifacts and separate experimental semantic artifacts;
- task-scoped Context Packs with bounded output;
- explicit package/workspace evidence, Relationship Candidates, and Graph Quality Warnings;
- JavaScript and TypeScript workspace import and scoped alias resolution when local evidence is sufficient;
- Python CFG and lexical binding inspection through source-free experimental metadata;
- command risk buckets for candidate verification commands that remain found but not run;
- freshness, warning, limit, confidence, and truncation metadata;
- safe assistant orientation without whole-source disclosure.

Deferred or out of scope:

- PyPI publishing and Docker registry publishing;
- HTTP API or HTTP MCP serving;
- watch mode, Git hooks, or automatic background indexing;
- browser UI, graph visualization, or hosted service;
- AI-required graph generation, embeddings, hosted semantic enrichment, or AI prose summaries;
- write-capable MCP tools;
- runtime package registry lookups during indexing;
- deep semantic call graphs, data-flow, taint analysis, full compiler-level resolution, or runtime Python behavior proof.
