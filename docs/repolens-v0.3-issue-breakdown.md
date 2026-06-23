# RepoLens MCP v0.3 Issue Breakdown

Source documents:

- `docs/repolens-v0.3-plan.md`
- `docs/repolens-v0.3-release-tracker.md`
- `CONTEXT.md`
- `docs/adr/0003-v0-3-context-pack-boundary.md`

Issue labels to use when publishing:

- `v0.3`
- `P0` / `P1` / `P2`
- `area:context-pack`
- `area:mcp`
- `area:cli`
- `area:evaluation`
- `area:security`
- `area:docs`
- `area:package-workspace`

## P0 Slices

### 1. Context Pack contracts and fixture specification

Type: AFK

Blocked by: None - can start immediately

Suggested labels: `v0.3`, `P0`, `area:context-pack`, `area:security`, `area:evaluation`

## What to build

Define the contracts that implementation must follow before feature coding spreads response-shape decisions across the codebase. This slice should establish the Context Pack schema contract, deterministic ranking contract, safe Context Pack ID and item-handle rules, explicit support-group budgets, a central No Whole-Source Disclosure guard for pack output, and a concrete evaluation fixture manifest.

The fixture manifest should be concrete enough that later implementation slices can code against expected happy paths and safety negatives rather than inventing examples after the fact.

## Acceptance criteria

- [ ] The Context Pack schema contract defines required top-level fields, item kinds, per-item fields, support-group shapes, budget metadata, truncation metadata, expansion handles, confidence fields, and MCP envelope expectations.
- [ ] The deterministic ranking contract defines ranking inputs, scoring categories, confidence treatment, stable tie-breakers, and broad/no-match/ambiguous-task behavior.
- [ ] Context Pack ID and item-handle rules prohibit raw task text, secret-like task fragments, absolute paths, source snippets, serialized source-derived payloads, and session state.
- [ ] Support-group budgets are explicit, including First-Read Files, per-group support items, `next_actions`, Agent Guidance metadata, and overall character caps.
- [ ] A central No Whole-Source Disclosure guard exists for Context Pack output and rejects or sanitizes forbidden fields.
- [ ] The fixture manifest names representative happy-path tasks, test-focused tasks, documentation/config tasks, broad tasks, focal ambiguity cases, no-match cases, focus-hint cases, stale graph cases, secret-redaction cases, stale-pack cases, and no-source-disclosure cases.
- [ ] Human output contract uses softer lower-priority wording instead of “ignore” or strong deprioritization claims.

### 2. Context Pack tracer bullet

Type: AFK

Blocked by: Slice 1

Suggested labels: `v0.3`, `P0`, `area:context-pack`, `area:mcp`, `area:cli`

## What to build

Add the first end-to-end Context Pack path. Given a natural-language task, RepoLens should return a deterministic, bounded, file-centric Context Pack through MCP and a thin `repolens context` CLI.

This slice should implement the Context Pack service/model, version, deterministic Context Pack ID, redacted task output, default budget, First-Read Files, compact human CLI output, `--json`, MCP envelope integration, and deterministic tests against the slice 1 contracts. It should remain orientation-only and must pass through the central No Whole-Source Disclosure guard.

## Acceptance criteria

- [ ] `get_task_context` returns a v0.3 Context Pack envelope for a representative indexed repository.
- [ ] `repolens context <task>` uses the same Context Pack service as MCP.
- [ ] Context Packs include `context_pack_id`, `context_pack_version`, redacted task text, budget metadata, freshness metadata, First-Read Files, truncation metadata, and expansion handles.
- [ ] Context Pack output is deterministic for the same graph, task, focus hints, and budgets.
- [ ] The default budget follows the explicit support-group and character caps from the contract.
- [ ] Context Pack MCP and CLI output passes through the central No Whole-Source Disclosure guard.

### 3. Context Pack safety and ambiguity hardening

Type: AFK

Blocked by: Slice 1, Slice 2

Suggested labels: `v0.3`, `P0`, `area:context-pack`, `area:security`

## What to build

Harden Context Pack behavior for unsafe, stale, ambiguous, broad, and low-evidence inputs before expanding the amount of context the pack can return. The tool should fail safely, preserve user privacy, and avoid unsupported guesses.

## Acceptance criteria

- [ ] Missing or unavailable graph artifacts return the existing structured graph-unavailable error.
- [ ] Stale but readable graphs can return downgraded packs with freshness warnings.
- [ ] Tasks with no useful graph matches return successful low-confidence packs with no broad repository dump.
- [ ] Focal ambiguity returns candidates instead of silently choosing one target.
- [ ] Broad tasks return bounded packs with breadth warnings.
- [ ] Focus paths outside the analysis root are rejected.
- [ ] In-root unresolved focus paths or symbols warn and lower confidence.
- [ ] Secret-like task text and focus hints are redacted in all output, handles, evidence, and logs.
- [ ] Context Pack IDs and task fingerprints do not expose raw secret-like input.
- [ ] Safety negative cases from the fixture manifest are covered by tests before support-group expansion continues.

### 4. Evidence-gated support groups

Type: AFK

Blocked by: Slice 1, Slice 2, Slice 3

Suggested labels: `v0.3`, `P0`, `area:context-pack`, `area:security`

## What to build

Extend Context Packs with evidence-gated support context around the First-Read Files. The pack should surface likely tests, docs, configs, commands, Risk Signals, lower-priority context, Agent Guidance metadata, and safe next actions without becoming a broad repository dump.

## Acceptance criteria

- [ ] Likely tests appear in a separate group and are attached to relevant First-Read Files.
- [ ] Likely tests do not consume the default First-Read File budget unless the task is test-focused.
- [ ] Docs, configs, and commands appear only when task matching or graph relationships provide evidence.
- [ ] Agent Guidance appears only as tiny path/kind/freshness/reason metadata when indexed.
- [ ] Risk Signals include metadata only, not raw comment text.
- [ ] Lower-priority context is cautious and evidence-backed, not an absolute ignore list.
- [ ] Human output says “lower-priority context” or equivalent softened wording, not “ignore”.
- [ ] Candidate Verification Commands are capped, marked not run, and not recommended for automatic execution.
- [ ] Safe `next_actions` are limited to reading First-Read Files, expanding returned items, or explaining relevance.
- [ ] All support groups obey the explicit budgets from the slice 1 contract.

### 5. Derived Structural Summaries and package ownership

Type: AFK

Blocked by: Slice 1, Slice 2, Slice 4

Suggested labels: `v0.3`, `P0`, `area:context-pack`, `area:package-workspace`

## What to build

Add derived-on-demand Structural Summary helpers for the scopes needed by Context Packs. Summaries should improve orientation without duplicating graph facts, adding source excerpts, or persisting summary state prematurely.

## Acceptance criteria

- [ ] Context Packs can include Structural Summaries for relevant repository, package/workspace, directory, file, symbol, or test-group scopes when useful.
- [ ] Structural Summaries are derived from graph facts at query time.
- [ ] Structural Summaries include freshness/hash metadata where applicable.
- [ ] First-Read Files include explicit Package Boundary ownership when known.
- [ ] Package/workspace ownership is not inferred from directory names alone.
- [ ] Supporting docs may include indexed titles/headings as graph facts but not body excerpts.
- [ ] Symbol metadata is limited to structural names, kinds, qualified names, exported/public classification where known, and line ranges.
- [ ] Ranking ties use deterministic stable sort keys from the ranking contract.

### 6. Pack-scoped expansion and relevance

Type: AFK

Blocked by: Slice 1, Slice 2, Slice 3, Slice 4

Suggested labels: `v0.3`, `P0`, `area:context-pack`, `area:mcp`

## What to build

Add stateless progressive-disclosure tools for Context Packs. Assistants should be able to expand one returned item or ask why one returned item appeared, without RepoLens storing session memory or exposing source text.

## Acceptance criteria

- [ ] `expand_context` accepts a Context Pack ID and item handle for an item returned in that pack.
- [ ] `expand_context` expands only returned Context Pack items.
- [ ] Expansion defaults to depth 1 and has a hard maximum depth of 2.
- [ ] Expansion output is bounded by per-kind and total item caps.
- [ ] `explain_relevance` explains why an item appeared in a specific Context Pack.
- [ ] Stale or mismatched Context Pack IDs return structured `ok: false` errors requiring a new pack.
- [ ] Expansion and relevance outputs include reasons, confidence, evidence, and freshness metadata.
- [ ] Expansion and relevance outputs pass through the central No Whole-Source Disclosure guard.

### 7. Context Pack Evaluation execution

Type: AFK

Blocked by: Slice 1, Slice 2, Slice 3, Slice 4, Slice 5, Slice 6

Suggested labels: `v0.3`, `P0`, `area:evaluation`, `area:cli`

## What to build

Implement local Context Pack Evaluation so maintainers can measure whether v0.3 improves assistant orientation. Evaluation should use the concrete fixture manifest from slice 1, committed deterministic fixtures, dogfooding-derived distilled cases, and baselines against existing `suggest_reading_order` plus lexical matching.

## Acceptance criteria

- [ ] `repolens evaluate-context` runs committed Context Pack Evaluation fixtures derived from the slice 1 manifest.
- [ ] Evaluation compares Context Packs against `suggest_reading_order` and a simple lexical baseline.
- [ ] Evaluation records first-read hit rate, irrelevant file count, test inclusion, pack size, expansion count, and safety negative outcomes.
- [ ] Evaluation includes safety negative cases for no useful matches, focal ambiguity, broad tasks, stale graph warnings, invalid outside-root focus paths, unresolved in-root focus hints, secret-like task redaction, stale pack ID errors, and no-snippet enforcement.
- [ ] Release-blocking fixtures use expectation-based gates rather than universal numeric thresholds.
- [ ] Evaluation output is JSON suitable for CI and release-readiness evidence.

### 8. v0.3 docs and release readiness

Type: AFK

Blocked by: Slice 1, Slice 2, Slice 3, Slice 4, Slice 5, Slice 6, Slice 7

Suggested labels: `v0.3`, `P0`, `area:docs`

## What to build

Document the v0.3 Context Pack workflow for users and assistants, including MCP examples, CLI examples, evaluation usage, known limitations, and release readiness evidence.

## Acceptance criteria

- [ ] Assistant-facing docs explain `get_task_context`, `expand_context`, and `explain_relevance`.
- [ ] CLI docs explain `repolens context` and `repolens evaluate-context`.
- [ ] Examples show Context Packs as orientation-only bundles without source snippets.
- [ ] Known limitations document non-goals such as embeddings, LLM summaries, source snippets, full framework emulation, and persisted pack sessions.
- [ ] Release-readiness docs include the Context Pack Evaluation report and MCP/CLI smoke evidence.
- [ ] `docs/repolens-v0.3-release-tracker.md` is updated with issue references when issues are published.

## P1 Follow-Up Candidates

### 9. Navigation gap improvements from evaluation

Type: AFK

Blocked by: Slice 7

Suggested labels: `v0.3`, `P1`, `area:package-workspace`, `area:context-pack`

## What to build

Improve generic package, workspace, route, command, or test navigation only where Context Pack Evaluation or dogfooding shows a concrete gap.

## Acceptance criteria

- [ ] Each navigation improvement links to an evaluation or dogfooding finding.
- [ ] Improvements use explicit repository evidence rather than framework/runtime emulation.
- [ ] Updated evaluation fixtures demonstrate the improvement.

### 10. Persisted summary caching if needed

Type: AFK

Blocked by: Slice 5, Slice 7

Suggested labels: `v0.3`, `P1`, `area:context-pack`

## What to build

Add persisted Structural Summary caching only if evaluation shows derived summaries are too slow or unstable.

## Acceptance criteria

- [ ] A performance or stability finding justifies persisted summary caching.
- [ ] Cached summaries remain deterministic and tied to graph freshness/hash metadata.
- [ ] Cache invalidation is covered by tests.

### 11. Additional evaluation corpora

Type: AFK

Blocked by: Slice 7

Suggested labels: `v0.3`, `P1`, `area:evaluation`

## What to build

Expand Context Pack Evaluation beyond the release-blocking representative fixtures using additional distilled fixtures and dogfooding-derived task cases.

## Acceptance criteria

- [ ] Additional fixtures cover at least one new repository shape or task family.
- [ ] New fixtures are deterministic and do not vendor third-party repository snapshots.
- [ ] Evaluation reports distinguish release-blocking fixtures from expanded corpora.
