# RepoLens MCP v0.5 Assistant Usage Guide

RepoLens gives coding assistants deterministic, read-only repository orientation before they open source files. In v0.5, start each task with Assistant Preflight: a bounded, task-scoped contract with graph freshness, first-read files, likely tests, candidate verification commands, warnings, focus hints, confidence, limits, and truncation metadata.

Assistant Preflight and Context Packs are orientation-only. They do not include source snippets, function or method signatures, code bodies, raw comments, paragraph excerpts, raw Agent Guidance instructions, or persisted assistant session state. Use them to choose what to read next, not as a substitute for reading files before editing.

## Setup Flow

1. Index the target repository:

```bash
repolens index /absolute/path/to/repo
```

2. Configure your MCP client to start RepoLens over stdio:

```bash
repolens mcp /absolute/path/to/repo
```

3. Ask the assistant to call `assistant_preflight` before broad file exploration. The preflight response includes graph freshness and bounded task context.

## Recommended Assistant Prompt

```text
Use RepoLens MCP for this repository before broad file exploration. For each task, call assistant_preflight with the task description first. Inspect graph freshness, warnings, budget controls, focus hints, first-read files, likely tests, and candidate verification commands. Treat the response as orientation metadata, not source code. Read the returned files directly before editing. Candidate commands are found by RepoLens, not run by RepoLens, and must not be executed automatically.
```

For edit-planning tasks:

```text
Before editing, call assistant_preflight for the task. Read the top First-Read Files yourself, then use get_task_context or expand_context only when you need bounded follow-up context. Use explain_relevance when you need to understand why an item appeared. Treat candidate_verification_commands as commands found in the repository, not commands RepoLens ran or recommends for automatic execution.
```

## Assistant Preflight Workflow

1. Call `assistant_preflight` with the natural-language task before broad file reads.
2. Check `freshness`, `warnings`, `limits`, `truncation`, `confidence`, and `budget_controls` before trusting ranked items.
3. Read `first_read_files` first, then inspect `likely_tests`, `supporting_docs`, `supporting_configs`, `risk_signals`, and `candidate_verification_commands` as needed.
4. Use `focus_hint` or `--focus-hint` when the task names a repo-relative path, module, package, or symbol and the initial result is too broad.
5. If artifacts are missing or require rebuild, ask the user to run `repolens index` or `repolens update`; MCP tools remain read-only and do not update artifacts.
6. If a follow-up Context Pack is needed, request it for the same task instead of asking RepoLens for source snippets.

## Context Pack Workflow

1. Call `graph_status` to check whether graph artifacts are available and fresh enough for planning.
2. Call `get_task_context` with the natural-language task.
3. Read the returned `warnings`, `freshness`, `limits`, `truncation`, and `confidence` before trusting the ranked items.
4. Inspect `first_read_files` first. Use `likely_tests`, `supporting_docs`, `supporting_configs`, `risk_signals`, and `candidate_verification_commands` as bounded support context.
5. Use `expand_context` only with an `item_handle` returned by the same Context Pack and the same task. Expansion is stateless, defaults to depth 1, and is capped.
6. Use `explain_relevance` to inspect the reason, confidence, evidence, and freshness for one returned item without broadening scope.
7. If a follow-up call returns `ok: false` because the pack is stale or mismatched, request a fresh `get_task_context` pack instead of reusing old handles.

## Context Pack Rules For Assistants

- Treat `first_read_files` as a starting reading set, not guaranteed edit files.
- Treat `lower_priority_context` as context to inspect later if needed, not an ignore list.
- Treat ambiguous results as candidates. Do not silently pick one target when RepoLens reports ambiguity.
- Treat no-match results as useful negative orientation. Do not compensate by asking for a repository dump.
- Never ask RepoLens for source snippets through Context Pack tools. They intentionally return metadata only.
- Never execute candidate verification, deploy, publish, or package-manager commands automatically just because RepoLens detected them.

## OpenCode Example

Use `docs/opencode-mcp.example.jsonc` as a documentation-only shape. Keep active OpenCode config outside this repository unless you intentionally want to commit it.

Local checkout form:

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

Installed CLI form:

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

Docker form:

```json
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
        "--network",
        "none",
        "--user",
        "1000:1000",
        "-v",
        "/absolute/path/to/repo:/workspace",
        "repolens:latest",
        "mcp",
        "/workspace"
      ],
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

Replace `1000:1000` with the output of `id -u` and `id -g` on the host.

After connecting OpenCode, instruct the assistant to call `assistant_preflight` before broad file reads.

## Claude Desktop Example

Claude Desktop uses an `mcpServers` object. For local contributor development from this repository:

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

For an installed CLI, use `"command": "repolens"` and `"args": ["mcp", "/absolute/path/to/repo"]`.

## Cursor-Style MCP Example

Cursor-style MCP config also uses an `mcpServers` object:

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

Keep active editor config local unless you intentionally want to share it. After connecting, ask Cursor to call `assistant_preflight` before broad file reads.

## Setup Diagnostics

Run these checks before connecting an assistant:

```bash
uv run repolens --help
uv run repolens index /absolute/path/to/repo
uv run repolens status /absolute/path/to/repo
uv run repolens preflight /absolute/path/to/repo "Check setup" --json
```

Expected result: status reports available artifacts, preflight reports freshness and bounded orientation metadata, and candidate verification commands remain marked as found but not run.

## Docker And PyPI Readiness Smokes

Docker smoke without registry publishing:

```bash
docker build -t repolens:latest .
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest index /workspace
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest preflight /workspace "Check Docker setup" --json
```

PyPI readiness smoke without publishing:

```bash
uv build --out-dir /tmp/repolens-dist --clear
uv tool install --force /tmp/repolens-dist/*.whl
repolens --help
repolens preflight /absolute/path/to/repo "Check wheel setup" --json
uv tool uninstall repolens
```

These commands build and exercise local artifacts only. They do not publish to PyPI, push a Docker image, contact a package registry at runtime, or start a hosted service.

## Assistant Operating Rules

- Prefer `graph_status` before any other RepoLens tool.
- Prefer `assistant_preflight` as the first task-specific call before broad file reads.
- Use `get_task_context` for bounded follow-up Context Packs when preflight is not enough.
- Use `expand_context` only for returned Context Pack item handles.
- Use `explain_relevance` to inspect why a returned item appears in the pack.
- Use `repo_summary`, `suggest_reading_order`, and `impact_analysis` as lower-level graph tools when you need repository shape, a legacy reading-order baseline, or target-based impact context.
- Use `search_graph` for graph metadata and `search_text` only when bounded live-text previews are needed.
- Treat `candidate_verification_commands` as commands found in the repository, not commands that RepoLens ran or recommends for automatic execution.
- Do not ask RepoLens to write files, update artifacts, execute commands, or publish releases through MCP. It cannot and should not do those things.

## When To Reindex

Run `repolens update /absolute/path/to/repo` after local file changes. Run `repolens index /absolute/path/to/repo` when status reports `rebuild_required`, when schema compatibility changes, or when you want a full deterministic rebuild.
