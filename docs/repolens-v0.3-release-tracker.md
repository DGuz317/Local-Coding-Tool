# RepoLens MCP v0.3 Release Tracker

Release theme:

```text
Make RepoLens the assistant's context budget manager.
```

Release integration branch: `feature/repolens-v0.3`

GitHub umbrella tracker: TBD

## Source Documents

- `docs/repolens-v0.3-plan.md`
- `docs/repolens-v0.3-issue-breakdown.md`
- `CONTEXT.md`
- `docs/adr/0003-v0-3-context-pack-boundary.md`
- `docs/adr/0001-standardize-mcp-envelope.md`
- `docs/adr/0002-edge-contract-storage.md`

## Release-Blocking P0 Work

- [ ] Add Context Pack schema, ranking, handle, budget, disclosure-guard, and evaluation fixture contracts.
- [ ] Add Context Pack service/model, deterministic Context Pack IDs, `get_task_context` MCP tool, and thin `repolens context` CLI.
- [ ] Add early task redaction, no-snippet, stale/missing graph, stale-pack, ambiguity, broad-task, and focus-hint safety hardening.
- [ ] Add evidence-gated support groups for tests, docs, configs, commands, Risk Signals, Deprioritized Context, and tiny Agent Guidance metadata.
- [ ] Add derived Structural Summary helpers for Context Packs.
- [ ] Add pack-scoped `expand_context` and `explain_relevance` MCP tools.
- [ ] Add local Context Pack Evaluation fixtures, safety negative cases, and `repolens evaluate-context`.
- [ ] Add v0.3 assistant docs, MCP examples, CLI examples, and known limitations.

## Non-Blocking P1 Work

- [ ] Improve generic package/workspace/framework navigation when evaluation shows gaps.
- [ ] Add persisted Structural Summary caching if derived summaries are too slow or unstable.
- [ ] Add richer human formatting for `repolens context` if JSON/human parity becomes painful.
- [ ] Expand Context Pack Evaluation corpora beyond the release-blocking representative fixtures.

## Dependency Notes

- Schema, ranking, handle, budget, disclosure-guard, and fixture contracts start the P0 implementation path.
- `get_task_context` depends on deterministic Context Pack IDs and the Context Pack output model.
- Safety hardening should land before support-group and summary expansion.
- `expand_context` and `explain_relevance` depend on pack IDs, item handles, stale-pack validation, and the central No Whole-Source Disclosure guard.
- Context Pack Evaluation execution depends on concrete fixture definitions, `get_task_context`, and baselines for existing `suggest_reading_order` and lexical matching.
- Docs and release-readiness examples depend on final MCP/CLI output shapes.

## Release Criteria

Do not cut a v0.3 release until all release-blocking P0 items above are complete and the release gate has evidence for:

- `get_task_context` returns deterministic, bounded, file-centric Context Packs for representative tasks.
- Context Pack schema, ranking, item-handle, pack-ID, and support-budget contracts are explicit before implementation.
- Context Packs include redacted task text only, never raw task text or source snippets.
- First-Read Files include reasons, confidence, evidence, relevant structural symbols, and expansion handles.
- Likely tests are included where known and do not consume the default First-Read File budget unless the task is test-focused.
- Support groups have explicit budgets; docs, configs, commands, Risk Signals, and Deprioritized Context are evidence-gated and capped; Agent Guidance appears only as tiny metadata when present.
- Candidate Verification Commands are marked not run and not recommended for automatic execution.
- Safe `next_actions` metadata is limited to reading First-Read Files, expanding returned items, or explaining relevance.
- Human output uses softer lower-priority wording instead of “ignore” or strong deprioritization claims.
- A central No Whole-Source Disclosure guard protects Context Pack MCP and CLI outputs.
- Missing graphs return structured graph-unavailable errors; stale readable graphs return downgraded packs with freshness warnings.
- Stale or mismatched Context Pack IDs require requesting a new pack for expansion or relevance explanation.
- Invalid focus paths outside the analysis root are rejected; unresolved in-root hints warn and lower confidence.
- `expand_context` expands only returned Context Pack items with bounded depth and item caps.
- `explain_relevance` explains why an item appeared in a specific Context Pack.
- Context Pack Evaluation shows no worse than baseline behavior on representative fixtures and records first-read hit rate, irrelevant file count, test inclusion, pack size, expansion count, and safety negative outcomes.
- Full verification passes: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/repolens`.
- MCP smoke covers `get_task_context`, `expand_context`, and `explain_relevance`.
- CLI smoke covers `repolens context` and `repolens evaluate-context`.

## Known Limitation Policy

Known limitations are acceptable when they are explicit, safe, and do not undermine Context Pack trust.

Document limitations instead of silently resolving when behavior would require:

- AI or embedding-based task matching.
- LLM-generated summaries or graph facts.
- Source snippets, code signatures, function bodies, paragraph excerpts, or raw comment text in Context Packs.
- Runtime Python import emulation.
- Full TypeScript compiler, package manager, bundler, or framework resolution.
- Server-side assistant session memory or persisted Context Pack snapshots.
- Telemetry, hosted evaluation, browser UI, or write-capable MCP behavior.

Promote a limitation to P0 bug work when evaluation or dogfooding shows it causes unsafe assistant guidance, source disclosure risk, stale or misleading Context Pack expansion, unusable assistant orientation, or repeated failure to include known relevant files/tests.

## Tracker Maintenance

- Keep this file aligned with `docs/repolens-v0.3-plan.md` as decisions change.
- Add GitHub issue numbers after the plan and tracker are stable.
- Use a small issue label taxonomy: `v0.3`, `P0/P1/P2`, `area:context-pack`, `area:mcp`, `area:cli`, `area:evaluation`, `area:security`, `area:docs`, and `area:package-workspace`.
- Keep P0/P1 separation visible in both local docs and future GitHub tracker/issues.
- Do not close the future umbrella tracker until the v0.3 release gate is satisfied or the release scope is explicitly abandoned.
