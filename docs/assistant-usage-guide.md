# RepoLens MCP v0.2 Assistant Usage Guide

RepoLens gives coding assistants deterministic, read-only repository context before they open source files. Use it as planning context, not as a replacement for reading the specific files you will edit.

## Setup Flow

1. Index the target repository:

```bash
repolens index /absolute/path/to/repo
```

2. Configure your MCP client to start RepoLens over stdio:

```bash
repolens mcp /absolute/path/to/repo
```

3. Ask the assistant to check graph freshness before relying on graph facts.

## Recommended Assistant Prompt

```text
Use RepoLens MCP for this repository before broad file exploration. Start with graph_status. If the graph is fresh, use repo_summary and suggest_reading_order to choose the first files to inspect. Treat RepoLens output as static, evidence-backed planning context, not as a substitute for reading files before editing. If graph_status reports stale, missing, or rebuild_required artifacts, ask before relying on graph facts.
```

For edit-planning tasks:

```text
Before editing, call impact_analysis for the file, symbol, or package you plan to change. Use related files, tests, docs, configs, risks, and candidate verification commands as planning context. Do not execute deploy or publish commands automatically.
```

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
- Use `repo_summary` for repository shape, languages, entrypoints, and commands.
- Use `suggest_reading_order` to choose a small initial reading set for a task.
- Use `impact_analysis` before edits to discover likely dependencies, dependents, related tests, docs, configs, and risks.
- Use `search_graph` for graph metadata and `search_text` only when bounded live-text previews are needed.
- Treat `candidate_verification_commands` as commands found in the repository, not commands that RepoLens ran or recommends for automatic execution.
- Do not ask RepoLens to write files, update artifacts, execute commands, or publish releases through MCP. It cannot and should not do those things.

## When To Reindex

Run `repolens update /absolute/path/to/repo` after local file changes. Run `repolens index /absolute/path/to/repo` when status reports `rebuild_required`, when schema compatibility changes, or when you want a full deterministic rebuild.
