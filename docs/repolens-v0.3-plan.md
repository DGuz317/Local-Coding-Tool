# RepoLens MCP v0.3 Plan

Working theme:

```text
Turn the repository graph into the smallest trustworthy context bundle an assistant needs before editing.
```

## Positioning

After v0.2 makes RepoLens more reliable on real repositories, v0.3 should focus on making RepoLens economical for AI assistants.

The goal is not to collect more graph facts for their own sake. The goal is to reduce the time and token cost required for an assistant to understand enough of a codebase to act safely.

RepoLens should help an assistant answer:

- What should I read first?
- Why is this file or symbol relevant?
- What appears lower priority for now?
- Which tests, docs, configs, commands, or entrypoints are likely relevant?
- How much confidence should I place in this context?

## Main Goal

v0.3 should optimize for task-scoped context compression:

```text
Given a user task, return the smallest useful, evidence-backed context bundle needed before editing.
```

Success means assistants open fewer irrelevant files, spend fewer tokens on orientation, and reach useful edits faster.

## Top Priorities

### 1. Context Packs

RepoLens should expose a task-oriented context tool that accepts a natural-language task, optional focus hints, and bounded budget parameters, then returns a Context Pack.

A Context Pack is a new v0.3 concept, distinct from v0.2 Impact Analysis. Impact Analysis remains a target-based evidence source inside the broader task-scoped pack.

Example input:

```text
Fix the auth timeout bug.
```

Initial output groups:

- `task`, containing redacted task text only
- `task_fingerprint`
- `context_pack_id`
- `context_pack_version`
- `budget`
- `freshness`
- `first_read_files`
- `likely_tests`
- `supporting_docs`
- `supporting_configs`
- `agent_guidance`
- `candidate_verification_commands`
- `risk_signals`
- `deprioritized_context`
- `ambiguity`
- `truncation`
- `expansion_handles`
- `next_actions`

The Context Pack should be deterministic, graph-derived, and file-centric. The primary ranked unit is a First-Read File, with relevant symbols, explicit package/workspace ownership when known, related tests, supporting docs/configs/commands, risks, reasons, confidence, and expansion handles attached or grouped alongside it.

Context Packs should be orientation bundles, not source-preview bundles. They should include structural metadata and summaries, but no source snippets, code signatures, function bodies, paragraph excerpts, or raw comment text. Risk signals should include location, category, reason, confidence, and evidence, not comment text.

Task matching should remain deterministic: split identifiers and paths, normalize simple lexical differences, match indexed symbols/docs/configs/commands, and return low-confidence candidates for ambiguous or fuzzy matches. v0.3 should not add embeddings, AI intent classification, synonym inference, or runtime package/framework lookups.

Before feature implementation starts, v0.3 should have an explicit Context Pack schema contract. The contract should define required top-level fields, item kinds, per-item fields, support-group shapes, budget metadata, truncation metadata, expansion handle shape, confidence fields, and MCP envelope expectations. Implementation slices should change the contract deliberately rather than letting response shape emerge from code.

Before feature implementation starts, v0.3 should also define a deterministic ranking contract. The contract should identify ranking inputs, scoring categories, confidence treatment, stable tie-breakers, and how broad/no-match/ambiguous tasks avoid unsupported guesses. The same graph, task, focus hints, and budget parameters must produce the same Context Pack order.

Context Pack IDs and item handles should be safe deterministic references, not serialized user input or source-derived payloads. They must not expose raw task text, secret-like task fragments, absolute paths, source snippets, or session state. Item handles should identify returned pack items by stable kind/path/node identifiers plus pack context, and stale or mismatched handles should fail clearly.

Context Pack generation should use a central No Whole-Source Disclosure guard before returning MCP or CLI output. The guard should reject or sanitize forbidden fields such as source snippets, function bodies, code signatures, paragraph excerpts, raw comment text, raw task text, or secret-like handle material.

### 2. Progressive Disclosure MCP Tools

RepoLens should avoid large one-shot responses when an assistant only needs orientation.

MCP tools should support stateless progressive exploration patterns such as:

- summary first
- expand this returned item
- show only high-confidence relationships
- show the next few files to inspect
- explain why this item is relevant
- continue from a deterministic Context Pack ID and item handle

This keeps assistant context small and lets the model request more only when needed.

Progressive disclosure should not require server-side session memory or persisted pack state. Expansion and relevance tools should operate on deterministic pack IDs, item handles, current graph freshness/hash validation, and bounded recomputation.

### 3. Stable Multi-Level Summaries

RepoLens should add deterministic Structural Summaries at multiple levels:

- repository
- package or workspace
- directory
- file
- symbol
- test group

These summaries should be derived on demand from graph facts in the first implementation, with deterministic output and freshness/hash metadata. Persisted summary tables or summary artifacts should wait until evaluation shows a concrete need.

The first implementation should use structural summaries rather than LLM-generated prose or source excerpts. Optional AI summaries can come later, but the core product should remain useful without an AI model, embeddings, hosted services, or runtime network access.

### 4. Reading Order Quality Metrics

v0.3 should measure whether RepoLens actually reduces assistant effort.

Context Pack Evaluation should use local deterministic fixtures and dogfooding-derived distilled cases. Useful metrics include:

- fewer source files opened before the first useful edit
- fewer irrelevant files opened
- smaller context used per task
- better inclusion of relevant tests
- faster task orientation
- better first-read ordering in dogfooding tasks
- first-read hit rate against expected main files where known
- irrelevant file count against baseline methods
- expansion count before finding expected context

The first release gate should use expectation-based checks rather than universal numeric thresholds: no worse than baseline methods on representative fixtures, known main implementation files appear in the default top five where applicable, likely tests are included where known, packs stay within budget, and every recommendation has evidence.

Evaluation should include safety negative cases for no useful matches, focal ambiguity, broad task breadth warnings, stale graph warnings, invalid outside-root focus paths, unresolved in-root focus hints, secret-like task redaction, stale pack ID errors, and no-snippet enforcement.

The initial evaluation fixture manifest should be concrete before coding starts. It should name representative happy-path tasks, test-focused tasks, documentation/config tasks, broad tasks, focal ambiguity cases, no-match cases, focus-hint cases, stale graph cases, secret-redaction cases, stale-pack cases, and no-source-disclosure cases, with expected outcomes for each.

### 5. Navigation-Oriented Package And Framework Awareness

RepoLens should improve package, workspace, route, command, and test relationships only where they improve task context selection.

This means prioritizing relationships that help answer:

- Which package owns this task?
- Which entrypoint reaches this code?
- Which tests are likely related?
- Which config controls this behavior?
- Which command might verify this change?

v0.3 should stay generic and evidence-based: package/workspace ownership, declared entrypoints, commands, test configs, and explicit route/config facts already visible in repository files. Full compiler, bundler, framework, or runtime emulation should remain out of scope unless dogfooding proves it is necessary for useful context selection.

## Resolved Scope Decisions

- v0.3 assumes the completed v0.2 graph/query/MCP contract as its baseline and does not support pre-v0.2 graph compatibility paths.
- Context Packs enforce deterministic item and character budgets and report approximate token estimates as metadata only.
- The default initial Context Pack should be small: five First-Read Files, at most five items per support group, at most three safe `next_actions`, tiny Agent Guidance metadata, and a conservative character cap around 12k.
- Likely tests should be grouped separately and attached to relevant First-Read Files. They should not consume the default First-Read File budget unless the task is explicitly test-focused.
- Docs, configs, and commands should be evidence-gated, not included as general repo orientation by default. Agent Guidance is the exception: when indexed, it may appear as tiny path/kind/freshness/reason metadata because it can constrain any edit.
- Candidate verification commands should be capped, related to selected context, marked not run, and never recommended for automatic execution.
- Deprioritized Context may appear only as cautious, evidence-backed lower-priority context, not an absolute ignore list. Human output should label this as lower-priority context rather than “deprioritized” or “ignore”.
- Broad tasks should return a bounded pack with a breadth warning, not an automatically expanded context dump.
- Missing or unavailable graph artifacts should return the existing structured graph-unavailable error. Stale but readable graphs may return downgraded packs with freshness warnings.
- Invalid focus paths outside the analysis root are errors. In-root unresolved paths or symbols are warnings that lower confidence.
- Context Pack output should never include raw task text; it should include redacted task text and may include a stable fingerprint.
- Context Packs may include safe `next_actions` metadata for reading First-Read Files, expanding returned items, or explaining relevance. They should not suggest automatic command execution, edits, or broad source search.

## Non-Goals

v0.3 should not prioritize:

- browser UI
- hosted sync
- telemetry
- write-capable MCP tools
- required embeddings or vector database
- required LLM-generated graph facts
- deep semantic call graphs
- full Python runtime import emulation
- full TypeScript compiler or bundler resolution
- cloud dashboard
- automatic code editing

## Product Shape

The ideal assistant workflow should become:

1. User gives a task.
2. Assistant asks RepoLens for a task-aware context pack.
3. RepoLens returns a small ranked set of First-Read Files plus evidence-gated tests, docs, configs, commands, risks, deprioritized context, and tiny Agent Guidance metadata when present.
4. Assistant reads only the highest-value files first.
5. Assistant expands returned items only when the graph evidence says it is useful.
6. Assistant edits with better orientation and lower token spend.

## MCP Capabilities

New MCP tools:

- `get_task_context`: return a bounded task-aware context pack.
- `expand_context`: expand one returned context pack item by a small bounded amount.
- `explain_relevance`: explain why an item appears in a specific context pack.

Existing lower-level tools should remain available and not be deprecated in v0.3:

- `impact_analysis`: target-based edit-planning context and one Context Pack evidence source.
- `suggest_reading_order`: file-ranking primitive and evaluation baseline.

The following should stay internal unless dogfooding proves assistants need direct access:

- `get_scope_summary`: summarize a repo, package, directory, file, or symbol.
- `rank_reading_order`: rank files for a task with reasons and limits.

All tools should keep the existing RepoLens principles:

- read-only MCP behavior
- bounded output
- no whole-source disclosure
- confidence and evidence
- stale/missing graph handling
- deterministic local-first behavior
- no command execution

## CLI And Evaluation Surface

v0.3 should add a thin `repolens context <task>` CLI that reuses the same Context Pack service as MCP. It should follow existing CLI conventions: human-readable compact output by default and `--json` for the full Context Pack envelope.

v0.3 should add `repolens evaluate-context` for local Context Pack Evaluation fixtures and release reporting. It should emit JSON suitable for CI and release-readiness evidence.

## Implementation Slices

Suggested vertical slice order:

1. Add the Context Pack schema, ranking, handle, budget, disclosure-guard, and evaluation fixture contracts.
2. Add the Context Pack service/model, deterministic Context Pack IDs, `get_task_context`, and thin `repolens context` CLI.
3. Add early safety and ambiguity hardening around task redaction, stale/missing graphs, invalid hints, broad tasks, no matches, and no-source-disclosure enforcement.
4. Add evidence-gated support groups and derived Structural Summary helpers.
5. Add pack-scoped `expand_context` and `explain_relevance`.
6. Add local Context Pack Evaluation execution through `repolens evaluate-context`.
7. Add v0.3 docs and release tracker updates.

## Release Criteria Ideas

v0.3 should be considered successful when dogfooding shows that, for representative tasks, RepoLens can:

- recommend a small first-read set that includes the main implementation file
- include likely related tests when they exist
- explain each recommendation with graph evidence
- avoid large irrelevant context dumps
- support follow-up expansion without requiring broad source search
- reduce the number of files an assistant opens during orientation
- stay safe under the No Whole-Source Disclosure guarantee

Release verification should include the existing full gate plus Context Pack evaluation once implemented:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/repolens`
- Context Pack Evaluation fixtures/report
- MCP smoke for `get_task_context`, `expand_context`, and `explain_relevance`
- CLI smoke for `repolens context`

## Suggested Version Theme

If v0.2 is:

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

Then v0.3 should be:

```text
Make RepoLens the assistant's context budget manager.
```
