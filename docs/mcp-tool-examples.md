# RepoLens MCP v0.6 Tool Examples

All RepoLens MCP tools are read-only and return the standard MCP response envelope with `ok`, `data`, `warnings`, `limits`, `confidence`, `evidence`, `freshness`, and `truncation`. Some tools also return `pagination`.

Assistant Preflight and Context Pack tools return orientation metadata only. They must not expose full source files, source snippets, code bodies, function or method signatures, paragraph excerpts, raw comments, raw Agent Guidance instructions, raw secret-like task text, absolute host paths, or persisted assistant session state.

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

## Run Assistant Preflight

Use `assistant_preflight` as the first task-specific call before broad file reads.

```json
{
  "tool": "assistant_preflight",
  "arguments": {
    "task": "Fix the auth timeout bug",
    "focus_hint": "src/auth/session.py",
    "max_files": 8,
    "max_tests": 6,
    "max_commands": 5
  }
}
```

Expected response shape is the standard envelope with `data.assistant_preflight_version`, graph freshness, budget controls, focus hints, `data.first_read_files`, `data.likely_tests`, support groups, `data.candidate_verification_commands`, warnings, confidence, limits, and truncation metadata. Candidate verification commands are found repository facts and remain `run: false`; RepoLens does not execute them.

Read the returned first-read files directly before editing. Use follow-up Context Pack tools only when bounded orientation is still needed.

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

## Get A Task Context Pack

Use `get_task_context` for bounded follow-up orientation when preflight is not enough.

```json
{
  "tool": "get_task_context",
  "arguments": {
    "task": "Fix the auth timeout bug"
  }
}
```

Expected response shape is the standard envelope with `data.context_pack_id`, `data.context_pack_version`, `data.task_fingerprint`, `data.first_read_files`, `data.likely_tests`, support groups, `data.expansion_handles`, `data.next_actions`, `freshness`, `limits`, `warnings`, and truncation metadata. Returned items include repo-relative paths, structural symbol names and line ranges where available, relationship kinds, confidence, bounded evidence metadata, and freshness. They do not include source snippets.

Use `first_read_files` as the first files to inspect manually. Use support groups as bounded orientation. Use `lower_priority_context` only as context to inspect later if needed.

## Expand A Returned Context Item

Use `expand_context` only with an item handle returned by the same Context Pack. Expansion is stateless, defaults to depth 1, and enforces bounded item caps.

```json
{
  "tool": "expand_context",
  "arguments": {
    "task": "Fix the auth timeout bug",
    "context_pack_id": "cp_example1234567890",
    "item_handle": "item_example1234567890",
    "depth": 1,
    "max_items_per_kind": 3,
    "max_total_items": 10
  }
}
```

If the graph changed or the pack ID no longer matches the current graph state, RepoLens returns `ok: false` and requires a fresh `get_task_context` call. Do not reuse handles from older packs.

## Explain Why An Item Appeared

Use `explain_relevance` when an assistant needs the reason, confidence, evidence, and freshness for one returned item without expanding scope.

```json
{
  "tool": "explain_relevance",
  "arguments": {
    "task": "Fix the auth timeout bug",
    "context_pack_id": "cp_example1234567890",
    "item_handle": "item_example1234567890"
  }
}
```

The explanation is still orientation metadata. It must not be treated as proof that lower-priority context is irrelevant or safe to ignore.

## CLI Context Pack Examples

Human-readable Assistant Preflight:

```bash
repolens preflight /absolute/path/to/repo "Fix the auth timeout bug"
```

Machine-readable Assistant Preflight:

```bash
repolens preflight /absolute/path/to/repo "Fix the auth timeout bug" --json
```

Context Pack follow-up remains available when needed.

Human-readable task context:

```bash
repolens context /absolute/path/to/repo "Fix the auth timeout bug"
```

Machine-readable task context:

```bash
repolens context /absolute/path/to/repo "Fix the auth timeout bug" --json
```

Run the local Context Pack Evaluation fixture suite:

```bash
repolens evaluate-context
```

Emit CI-friendly JSON and fail when the expectation-based release gate fails:

```bash
repolens evaluate-context --json
```

The JSON includes deterministic `local_savings_summary` and per-case `local_savings`
fields comparing the Context Pack result with a local lexical path-search baseline. These
are fixture-local estimates for exploration cost, not telemetry, exact model-token claims,
or universal productivity scores.

Use a custom evaluation manifest:

```bash
repolens evaluate-context --manifest tests/fixtures/context_pack/evaluation_manifest.json --json
```

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
