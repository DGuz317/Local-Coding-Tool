# Context Pack Contract

This is the v0.3 assistant-facing contract for Context Packs. Implementation slices should import `src/repolens/context_pack_contract.py` and update this document deliberately when the contract changes.

## Assistant Preflight

Assistant Preflight is the v0.5 bounded orientation workflow assistants should call before broad repository reads. It is exposed through the CLI `repolens preflight` command and the read-only MCP `assistant_preflight` tool. Both surfaces use the same service and return the standard MCP envelope fields: `ok`, `data`, `confidence`, `evidence`, `freshness`, `limits`, `truncation`, and `warnings`.

Assistant Preflight `data` includes:

- `assistant_preflight_version`
- `context_pack_id`
- `context_pack_version`
- `task_context`
- `focus_hints`
- `budget_controls`
- `freshness`
- `first_read_files`
- `likely_tests`
- `candidate_verification_commands`
- `ambiguity`
- `warnings`
- `evidence`
- `confidence`
- `limits`
- `truncation`

`task_context` contains only redacted display metadata, a deterministic task fingerprint, and the bounded orientation scope. `focus_hints` contains redacted hint metadata and relies on Context Pack warnings for unresolved hints. `budget_controls` uses deterministic item caps and character caps: first-read file count, per-support-group item count, candidate command count, and total character count. It does not define model-specific token budgets.

Preflight freshness comes from graph metadata and carries the canonical graph hash, freshness boolean, status, source, and evidence count. Stale graphs return bounded successful responses when readable, with stale warnings and lowered trust instead of silently pretending the graph is current. Missing graph artifacts keep the existing graph-unavailable error envelope.

Candidate verification commands remain discovered metadata only. They must stay marked `found: true`, `run: false`, `not_run: true`, and `auto_run_recommended: false`, with risk classified separately from purpose.

Default Context Pack behavior remains deterministic and unenriched. Preflight currently reuses the default Context Pack shape; opt-in enrichment is reserved for later contract slices.

## Schema

Context Pack data must include these top-level fields inside the standard MCP response envelope `data` object:

- `context_pack_id`
- `context_pack_version`
- `task`
- `task_fingerprint`
- `budget`
- `freshness`
- `first_read_files`
- `likely_tests`
- `supporting_docs`
- `supporting_configs`
- `agent_guidance`
- `candidate_verification_commands`
- `risk_signals`
- `lower_priority_context`
- `ambiguity`
- `expansion_handles`
- `next_actions`
- `truncation`

Items must include `handle`, `kind`, `path`, `reason`, `confidence`, `evidence`, and `freshness`. First-Read Files also include `rank`, `symbols`, `relationships`, and `related_tests`. Structural symbol metadata may include names, kinds, qualified names, public/exported classification, and line ranges. It must not include signatures or bodies.

Supported item kinds are `first_read_file`, `likely_test`, `supporting_doc`, `supporting_config`, `agent_guidance`, `candidate_verification_command`, `risk_signal`, `lower_priority_context`, and `ambiguity_candidate`.

Expansion handles must include `handle`, `item_kind`, `context_pack_id`, `reason`, and `max_depth`. Handles are deterministic, pack-scoped references to items returned in the pack.

`expand_context` is a stateless follow-up operation. Callers provide the original task, Context Pack ID, and item handle; RepoLens reconstructs the current Context Pack from graph state and returns `ok: false` when the pack is stale, mismatched, or the item handle was not returned in that pack. Expansion defaults to depth 1, enforces a hard maximum depth of 2, and bounds output by per-kind and total item caps.

`explain_relevance` is a stateless follow-up operation. Callers provide the original task, Context Pack ID, and item handle; RepoLens returns the returned item's reason, confidence, bounded evidence, and freshness metadata without expanding source text.

## MCP Envelope

Context Pack MCP tools must return the standard envelope fields: `ok`, `data`, `confidence`, `evidence`, `freshness`, `limits`, `truncation`, and `warnings`. Structured errors use `ok: false` and the existing RepoLens error shape. Missing or unavailable graph artifacts use the existing graph-unavailable errors.

## Budgets

Default budgets are explicit and deterministic:

- First-Read Files: 5
- Per support group: 5
- `next_actions`: 3
- Agent Guidance metadata items: 3
- candidate verification commands: 5
- risk signals: 5
- total character cap: 12,000
- approximate token estimate divisor: 4

Likely tests are grouped separately and should not consume the default First-Read File budget unless the task is test-focused. Candidate verification commands must be marked not run, must not be recommended for automatic execution, and may expose a separate `risk_bucket` such as `verification_likely`, `quality_check_likely`, `build_likely`, `risky_or_external`, or `unknown`. Agent Guidance may expose only bounded metadata such as path, kind, freshness, and reason.

## Ranking

Ranking is deterministic for the same graph, task, focus hints, and budgets. Ranking inputs are the canonical graph hash, Context Pack version, normalized redacted task fingerprint, focus hints, budget parameters, graph relationships, indexed symbols/docs/configs/commands, and freshness metadata.

Scoring categories are direct path or symbol match, focus hint match, graph relationship strength, task token match, related test or config evidence, freshness penalty, and ambiguity penalty. Confidence is a ranking signal only after score ties: high before medium, medium before low, and none only for unavailable or unusable context.

Stable tie-breakers are item kind priority, repo-relative POSIX path, qualified symbol name, line range start, stable graph node ID, and handle.

Broad tasks return bounded packs with breadth warnings, not repository dumps. No-match tasks return successful low-confidence packs without broad dumps. Ambiguous tasks return candidates instead of silently choosing one target.

## IDs And Handles

Context Pack IDs and item handles are deterministic and pack-scoped. Allowed inputs are canonical graph hash, Context Pack version, normalized redacted task fingerprint, focus hints, budget parameters, and stable item identity.

IDs and handles must not contain raw task text, secret-like task fragments, absolute paths, source snippets, serialized source-derived payloads, or assistant session state.

## No Whole-Source Disclosure Guard

All Context Pack MCP, CLI, expansion, relevance, evaluation, log, handle, and fingerprint output must pass through the central guard in `repolens.context_pack_contract.guard_context_pack_output` before return. The guard rejects by default and can sanitize when a caller explicitly opts into omission/redaction.

Forbidden output includes full source files, source snippets, code bodies, function or method signatures, paragraph excerpts, raw comment text, raw Agent Guidance instruction text, raw secret-like task text or focus hints, absolute host paths, serialized source-derived payloads, and session state.

Allowed orientation metadata includes repo-relative file paths, structural symbol metadata, relationship kinds, confidence, bounded evidence metadata, freshness/hash metadata, capped not-run command metadata, and tiny Agent Guidance metadata.

## Human Wording

Human output must use softer wording such as `Lower-priority context to inspect later`. It must not tell assistants that files are irrelevant, safe to ignore, or guaranteed unaffected.

## Fixture Manifest

The release-blocking fixture manifest is `tests/fixtures/context_pack/evaluation_manifest.json`. It names representative cases for happy paths, test-focused tasks, documentation/config tasks, broad tasks, focal ambiguity, no matches, focus hints, stale graphs, secret redaction, stale pack IDs, and no-source-disclosure negatives.
