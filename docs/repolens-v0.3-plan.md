# RepoLens MCP v0.3 Plan Archive

Status: archived historical plan.

## Theme

```text
Make RepoLens the assistant's context budget manager.
```

## Positioning

After v0.2 made RepoLens reliable on real repositories, v0.3 focused on making RepoLens economical for AI assistants. The release goal was not more graph facts for their own sake; it was reducing the time and token cost required for an assistant to understand enough of a codebase to act safely.

## Main Goal

```text
Given a user task, return the smallest useful, evidence-backed context bundle needed before editing.
```

Success meant assistants opened fewer irrelevant files, spent fewer tokens on orientation, and reached useful edits faster.

## Core Product Concepts

### Context Packs

A Context Pack is a deterministic, graph-derived, file-centric, task-scoped orientation bundle. It includes ranked First-Read Files plus evidence-gated tests, docs, configs, commands, risks, lower-priority context, and tiny Agent Guidance metadata when useful.

Context Packs are not source-preview bundles. They do not include source snippets, code signatures, function bodies, paragraph excerpts, raw comment text, raw Agent Guidance text, raw task text, or secret-like handle material.

### Progressive Disclosure

v0.3 added stateless follow-up exploration patterns:

- summary first;
- expand a returned item;
- explain why an item is relevant;
- continue from a deterministic Context Pack ID and item handle;
- validate graph freshness/hash before expansion.

### Structural Summaries

Structural Summaries are deterministic, graph-derived summaries for repository, package/workspace, directory, file, symbol, or test-group scopes. v0.3 derived these on demand rather than persisting generated prose or AI summaries.

### Evaluation

Context Pack Evaluation measures whether RepoLens improves assistant orientation. Metrics include first-read hit rate, irrelevant file count, test inclusion, pack size, expansion count, and safety negative outcomes.

## Scope Decisions

- v0.3 assumes the completed v0.2 graph/query/MCP contract.
- Context Packs enforce deterministic item and character budgets.
- Default packs are small: five First-Read Files, capped support groups, capped next actions, tiny Agent Guidance metadata, and a conservative character budget.
- Likely tests are grouped separately and do not consume First-Read File budget unless the task is test-focused.
- Docs, configs, and commands are evidence-gated.
- Candidate verification commands are capped, marked not run, and never recommended for automatic execution.
- Lower-priority context is cautious and evidence-backed, not an ignore list.
- Broad tasks return bounded packs with breadth warnings.
- No-match tasks return low-confidence packs without repository dumps.
- Invalid focus paths outside the analysis root are errors; unresolved in-root hints are warnings.
- Context Pack IDs and handles must not expose raw task text, secret-like text, absolute paths, source snippets, serialized source-derived payloads, or session state.

## MCP And CLI Surface

New MCP tools:

- `get_task_context`
- `expand_context`
- `explain_relevance`

CLI additions:

- `repolens context <repo> <task> --json`
- `repolens evaluate-context <repo> --json`

Existing lower-level tools such as `impact_analysis` and `suggest_reading_order` remained available as evidence sources and baselines.

## Non-Goals

- Browser UI, hosted sync, telemetry, cloud dashboard, or write-capable MCP tools.
- Required embeddings, vector database, LLM-generated graph facts, or AI summaries.
- Deep semantic call graphs, full Python runtime import emulation, full TypeScript compiler/bundler resolution, or automatic code editing.

## Implementation Order

1. Context Pack contracts and fixture specification.
2. Context Pack tracer bullet through MCP and CLI.
3. Safety and ambiguity hardening.
4. Evidence-gated support groups.
5. Derived Structural Summaries and package ownership.
6. Pack-scoped expansion and relevance explanation.
7. Context Pack Evaluation execution.
8. v0.3 docs and release readiness.
