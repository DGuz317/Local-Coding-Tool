# RepoLens MCP v0.2 Tool Examples

All RepoLens MCP tools are read-only and return the standard MCP response envelope with `ok`, `data`, `warnings`, `limits`, `confidence`, `evidence`, `freshness`, and `truncation`. Some tools also return `pagination`.

## Check Graph Status

Use first in each assistant session.

```json
{
  "tool": "graph_status",
  "arguments": {
    "max_changed_files": 20
  }
}
```

If `ok` is `false` or `freshness.status` is `stale`, `missing`, or `rebuild_required`, reindex or ask the user before relying on graph facts.

## Summarize Repository Shape

```json
{
  "tool": "repo_summary",
  "arguments": {
    "max_entrypoints": 10,
    "max_commands": 10,
    "max_modules": 20,
    "max_important_files": 20
  }
}
```

Use this for languages, high-level counts, detected entrypoints, important files, and candidate commands.

## Get A Reading Order

```json
{
  "tool": "suggest_reading_order",
  "arguments": {
    "task": "change MCP response envelope handling",
    "max_files": 7
  }
}
```

Read the suggested files before editing. If the response is ambiguous or low-confidence, narrow the task or query a specific path or symbol.

## Analyze Edit Impact

```json
{
  "tool": "impact_analysis",
  "arguments": {
    "target": "src/repolens/mcp_server.py",
    "depth": 1,
    "max_results": 20
  }
}
```

Use this as deterministic edit-planning context. It is not a runtime reachability guarantee.

## Search Structured Graph Metadata

```json
{
  "tool": "search_graph",
  "arguments": {
    "query": "GraphQueryService",
    "max_results": 20,
    "offset": 0
  }
}
```

This searches indexed graph metadata only and does not read live source text.

## Search Bounded Live Text

```json
{
  "tool": "search_text",
  "arguments": {
    "query": "candidate_verification_commands",
    "case_sensitive": false,
    "max_results": 20
  }
}
```

This reads scanner-approved live files and returns capped, sanitized previews. It does not expose full source files.

## Resolve And Traverse Nodes

```json
{
  "tool": "get_node",
  "arguments": {
    "reference": "src/repolens/query.py"
  }
}
```

```json
{
  "tool": "get_neighbors",
  "arguments": {
    "reference": "src/repolens/query.py",
    "depth": 1,
    "direction": "both",
    "edge_kinds": null,
    "max_results": 50,
    "offset": 0
  }
}
```

Use `get_node` when a target is ambiguous, then use node IDs for follow-up traversal if needed.

## Find A Bounded Path

```json
{
  "tool": "shortest_path",
  "arguments": {
    "source": "src/repolens/mcp_server.py",
    "target": "src/repolens/query.py",
    "max_depth": 6,
    "edge_kinds": null
  }
}
```

Use for relationship discovery, not proof of runtime control flow.

## List Entrypoints

```json
{
  "tool": "list_entrypoints",
  "arguments": {
    "kind": null,
    "max_results": 20,
    "offset": 0
  }
}
```

Use to find CLIs, scripts, packages, and other detected entrypoints with evidence.

## Read The Generated Report

```json
{
  "tool": "get_graph_report",
  "arguments": {
    "max_chars": 20000
  }
}
```

The report text is capped and should be treated as a summary export, not as the authoritative store.
