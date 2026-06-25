# RepoLens MCP v0.3 Issue Breakdown Archive

Status: archived historical issue breakdown.

## Source Documents

- `docs/repolens-v0.3-plan.md`
- `docs/repolens-v0.3-release-tracker.md`
- `CONTEXT.md`
- `docs/adr/0003-v0-3-context-pack-boundary.md`

## Labels

- Version: `v0.3`
- Priority: `P0`, `P1`, `P2`
- Areas: `area:context-pack`, `area:mcp`, `area:cli`, `area:evaluation`, `area:security`, `area:docs`, `area:package-workspace`

## P0 Slices

| Slice | Issue | Summary |
|---|---|---|
| 1 | #80 | Context Pack schema, ranking, handle, budget, disclosure guard, and evaluation fixture contracts. |
| 2 | #81 | First end-to-end Context Pack path through `get_task_context` and `repolens context`. |
| 3 | #82 | Task redaction, no-snippet, stale/missing graph, stale-pack, ambiguity, broad-task, and focus-hint safety hardening. |
| 4 | #83 | Evidence-gated support groups for tests, docs, configs, commands, Risk Signals, lower-priority context, and Agent Guidance metadata. |
| 5 | #84 | Derived Structural Summary helpers and explicit package ownership for Context Packs. |
| 6 | #85 | Pack-scoped `expand_context` and `explain_relevance` MCP tools. |
| 7 | #86 | Local Context Pack Evaluation fixtures, safety negative cases, and `repolens evaluate-context`. |
| 8 | #87 | v0.3 assistant docs, MCP examples, CLI examples, known limitations, and release-readiness evidence. |

## P1 Follow-Ups

| Issue | Summary |
|---|---|
| #88 | Improve generic navigation only where evaluation shows gaps. |
| #89 | Add persisted Structural Summary caching only if derived summaries are too slow or unstable. |
| #90 | Expand Context Pack Evaluation corpora beyond release-blocking fixtures. |

## Dependency Notes

- Slice 1 starts the implementation path.
- Slice 2 depends on the contracts from Slice 1.
- Slice 3 depends on Slices 1 and 2 and must land before support expansion.
- Slice 4 depends on Slices 1 through 3.
- Slice 5 depends on Slice 4 and adds summaries/package ownership.
- Slice 6 depends on pack IDs, item handles, stale-pack validation, and the disclosure guard.
- Slice 7 depends on the complete Context Pack and expansion surfaces.
- Slice 8 depends on final MCP/CLI output shapes and evaluation evidence.

## Release-Blocking Behavior

v0.3 was not complete until Context Packs were deterministic, bounded, file-centric, evidence-backed, safe under No Whole-Source Disclosure, exposed through both MCP and CLI, evaluable through local fixtures, and documented for assistant use.
