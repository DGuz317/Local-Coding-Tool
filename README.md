# RepoLens MCP

RepoLens helps an AI coding assistant understand a repository before it starts opening files or editing code.

Think of it as a local map of your codebase:

- It scans a repository on your machine.
- It writes a generated graph under `.repolens/`.
- It lets assistants ask read-only questions about files, symbols, tests, docs, configs, and relationships.
- In v0.3, it can return a small task-focused **Context Pack** so an assistant knows what to read first.

RepoLens is local-first. Normal indexing and MCP usage do not require AI models, embeddings, telemetry, hosted services, a browser UI, or runtime network calls.

## What Problem Does This Solve?

AI coding assistants often waste context by reading too many files too early.

RepoLens gives the assistant a safer first step:

1. Build a graph of the repository.
2. Ask RepoLens for orientation.
3. Read the most relevant files after that.

RepoLens does not replace reading source code. It helps decide where to start.

## The Short Version

If you are working from this repository checkout, run:

```bash
uv sync
uv run repolens index .
uv run repolens status .
uv run repolens context . "Fix the auth timeout bug"
```

What those commands mean:

- `uv sync` installs the project environment.
- `uv run repolens index .` scans the current repository and creates `.repolens/`.
- `uv run repolens status .` checks whether the generated graph is available and fresh.
- `uv run repolens context . "..."` asks for a small Context Pack for one task.

Replace `.` with another repository path if you want to inspect a different project.

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

### 5. Ask For Task Context

```bash
uv run repolens context /path/to/repo "Fix the auth timeout bug"
```

The Context Pack is a bounded orientation result. It can include things like:

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
uv run repolens mcp /path/to/repo
```

Command meanings:

- `index`: rebuild RepoLens graph artifacts from scratch.
- `update`: update artifacts from detected local changes, or initialize if missing.
- `status`: check graph freshness without creating `.repolens/`.
- `report`: print the generated Markdown graph report.
- `search`: search scanner-approved live text with capped previews.
- `context`: return a v0.3 task-scoped Context Pack.
- `mcp`: start the read-only stdio MCP server for an assistant.

There is also a developer-oriented `benchmark-update` command for update-speed evidence.

For machine-readable output, commands that support it accept `--json`:

```bash
uv run repolens context /path/to/repo "Fix the auth timeout bug" --json
```

## Using RepoLens With An Assistant

RepoLens is most useful when an MCP client starts it for an assistant.

The basic flow is:

1. Index the repository first.
2. Configure your MCP client to run `repolens mcp /absolute/path/to/repo`.
3. Tell the assistant to ask RepoLens for graph status and task context before broad file exploration.

Index first:

```bash
uv run repolens index /absolute/path/to/repo
```

MCP command shape:

```bash
uv run repolens mcp /absolute/path/to/repo
```

Important: `repolens mcp` is not an interactive terminal command. It waits for JSON-RPC messages from an MCP client. If you run it manually, it should appear to sit there silently.

Recommended assistant prompt:

```text
Use RepoLens MCP for this repository before broad file exploration. Start with graph_status. If the graph is available, call get_task_context for the current task. Treat Context Packs as orientation metadata, not source code. Read the actual files before editing.
```

For more assistant setup details, see:

- `docs/assistant-usage-guide.md`
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

## What RepoLens Is Allowed To Do

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

## Roadmap And Non-Goals

RepoLens v0.3 focuses on local, deterministic, assistant-facing Context Packs.

Current focus:

- local CLI indexing, update, status, report, search, context, and read-only MCP serving;
- deterministic `.repolens/` graph artifacts;
- task-scoped Context Packs with bounded output;
- freshness, warning, limit, confidence, and truncation metadata;
- safe assistant orientation without whole-source disclosure.

Deferred or out of scope:

- PyPI publishing and Docker registry publishing;
- HTTP API or HTTP MCP serving;
- watch mode, Git hooks, or automatic background indexing;
- browser UI, graph visualization, or hosted service;
- AI-required graph generation, embeddings, or semantic enrichment;
- write-capable MCP tools;
- runtime package registry lookups during indexing;
- deep semantic call graphs or full compiler-level resolution.
