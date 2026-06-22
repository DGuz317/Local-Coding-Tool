# Troubleshooting RepoLens MCP v0.2

## `graph_status` Reports Missing Artifacts

Run:

```bash
repolens index /absolute/path/to/repo
```

Then restart the MCP client or retry `graph_status` after the client's tool cache refreshes.

## `graph_status` Reports Stale Artifacts

Run:

```bash
repolens update /absolute/path/to/repo
```

Use `repolens index /absolute/path/to/repo` if the status says a full rebuild is required.

## MCP Command Blocks Silently In A Terminal

This is expected. `repolens mcp <repo-path>` is a stdio server for an MCP client. It waits for JSON-RPC messages on stdin and should not print interactive prompts.

## OpenCode Cannot Start The Server

Check:

- The configured repository path is absolute.
- `repolens index /absolute/path/to/repo` has completed successfully.
- The command works outside OpenCode with `repolens --help` or `uv run repolens --help`.
- The `cwd` in the MCP config exists.
- Docker examples use a numeric `--user` value such as `1000:1000`, not a shell expression that the MCP client will not expand.
- Docker examples include `-i` because stdio MCP needs stdin.

## Docker Creates Root-Owned `.repolens` Files

Run Docker with the host user and group:

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/workspace" repolens:latest index /workspace
```

If root-owned artifacts already exist, fix ownership manually before rerunning RepoLens.

## Search Results Are Missing Expected Files

RepoLens only scans approved files inside the analysis root. Files may be skipped because they are ignored by `.gitignore`, match default excludes, exceed size caps, look binary or generated, are under `.repolens/`, or look secret-bearing by path or name.

## `suggest_reading_order` Is Empty Or Low Confidence

Try a narrower task with file names, module names, symbols, or feature terms. If the repository has mostly docs/config files or sparse relationships, use `search_graph`, `search_text`, and direct file inspection to supplement the graph.

## `impact_analysis` Does Not Include A Runtime Dependency

Impact Analysis is graph-derived edit-planning context, not runtime reachability. RepoLens does not emulate Python import execution, TypeScript compilers, bundlers, package managers, or framework-specific module resolution.

## Candidate Commands Were Not Run

Correct. RepoLens records candidate verification commands as repository facts. It does not execute them and must not recommend deploy or publish-like commands for automatic execution.

## Suspected Secret Exposure

Delete `.repolens/`, rotate any exposed secret, remove the secret from source, and regenerate artifacts. RepoLens has conservative redaction and secret-path skips, but it is not a full secret scanner.
