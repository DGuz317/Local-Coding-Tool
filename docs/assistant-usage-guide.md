# RepoLens MCP v0.3 Assistant Usage Guide

RepoLens gives coding assistants deterministic, read-only repository orientation before they open source files. In v0.3, start with a Context Pack: a bounded, task-scoped bundle of files, symbols, tests, docs, configs, commands, risks, reasons, confidence, freshness, and expansion handles.

Context Packs are orientation-only. They do not include source snippets, function or method signatures, code bodies, raw comments, paragraph excerpts, raw Agent Guidance instructions, or persisted assistant session state. Use them to choose what to read next, not as a substitute for reading files before editing.

## Setup Flow

1. Index the target repository:

```bash
repolens index /absolute/path/to/repo
```

2. Configure your MCP client to start RepoLens over stdio:

```bash
repolens mcp /absolute/path/to/repo
```

3. Ask the assistant to check graph freshness before relying on graph facts, then request a task-scoped Context Pack.

## Recommended Assistant Prompt

```text
Use RepoLens MCP for this repository before broad file exploration. Start with graph_status. If the graph is available, call get_task_context for the current task and inspect the ranked First-Read Files, likely tests, support groups, warnings, limits, freshness, and confidence. Treat Context Packs as static, evidence-backed orientation metadata, not source preview. If graph_status reports missing or rebuild_required artifacts, ask before relying on graph facts. If freshness is stale but readable, use the warning and lower confidence in your plan.
```

For edit-planning tasks:

```text
Before editing, call get_task_context for the task. Read the top First-Read Files yourself, then use expand_context only on returned item handles when you need bounded follow-up context. Use explain_relevance when you need to understand why an item appeared. Treat candidate_verification_commands as commands found in the repository, not commands RepoLens ran or recommends for automatic execution.
```

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

## Assistant Operating Rules

- Prefer `graph_status` before any other RepoLens tool.
- Use `get_task_context` as the v0.3 default for task-scoped orientation.
- Use `expand_context` only for returned Context Pack item handles.
- Use `explain_relevance` to inspect why a returned item appears in the pack.
- Use `repo_summary`, `suggest_reading_order`, and `impact_analysis` as lower-level graph tools when you need repository shape, a legacy reading-order baseline, or target-based impact context.
- Use `search_graph` for graph metadata and `search_text` only when bounded live-text previews are needed.
- Treat `candidate_verification_commands` as commands found in the repository, not commands that RepoLens ran or recommends for automatic execution.
- Do not ask RepoLens to write files, update artifacts, execute commands, or publish releases through MCP. It cannot and should not do those things.

## When To Reindex

Run `repolens update /absolute/path/to/repo` after local file changes. Run `repolens index /absolute/path/to/repo` when status reports `rebuild_required`, when schema compatibility changes, or when you want a full deterministic rebuild.
