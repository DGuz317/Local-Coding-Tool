# RepoLens MCP v0.3 Release Tracker Archive

Status: archived historical tracker.

## Theme

```text
Make RepoLens the assistant's context budget manager.
```

## Tracker

- Integration branch: `feature/repolens-v0.3`
- GitHub umbrella tracker: `#79`

## Source Documents

- `docs/repolens-v0.3-plan.md`
- `docs/repolens-v0.3-issue-breakdown.md`
- `CONTEXT.md`
- `docs/adr/0003-v0-3-context-pack-boundary.md`
- `docs/adr/0001-standardize-mcp-envelope.md`
- `docs/adr/0002-edge-contract-storage.md`

## Release-Blocking P0 Work

- `#80` Context Pack contracts and fixture specification.
- `#81` Context Pack tracer bullet.
- `#82` Context Pack safety and ambiguity hardening.
- `#83` Evidence-gated support groups.
- `#84` Derived Structural Summaries and package ownership.
- `#85` Pack-scoped expansion and relevance.
- `#86` Context Pack Evaluation execution.
- `#87` v0.3 docs and release readiness.

## Non-Blocking P1 Work

- `#88` Navigation gap improvements from evaluation.
- `#89` Persisted summary caching if needed.
- `#90` Additional evaluation corpora.

## Release Evidence

Latest issue `#87` evidence captured on 2026-06-24:

- `uv run repolens evaluate-context --json` returned `ok: true`; expectation-based release gate passed; 11/11 cases passed.
- `uv run repolens index .` followed by `uv run repolens context . "Document Context Pack workflow" --json` returned `ok: true` with bounded Context Pack metadata.
- Direct service calls for `get_task_context`, `expand_context`, and `explain_relevance` returned `ok: true` for one returned First-Read File handle.
- Smoke outputs used repo-relative paths and metadata; no source snippets were required or recorded in release docs.
- `#89` cache gate found no performance or stability evidence requiring persisted Structural Summary caching.

## Release Criteria Summary

v0.3 required evidence that:

- `get_task_context` returns deterministic, bounded, file-centric Context Packs;
- Context Pack schema, ranking, item-handle, pack-ID, and budget contracts are explicit;
- Context Packs include redacted task text only and never source snippets;
- First-Read Files include reasons, confidence, evidence, structural symbols, and expansion handles;
- support groups are evidence-gated and capped;
- Candidate Verification Commands are marked not run;
- No Whole-Source Disclosure protects MCP and CLI output;
- missing/stale graph and stale-pack cases fail safely;
- `expand_context` and `explain_relevance` are bounded and pack-scoped;
- Context Pack Evaluation passes expectation-based gates;
- full verification and MCP/CLI smoke pass.

## Known Limitation Policy

Document limitations rather than silently resolving when behavior would require AI task matching, embeddings, LLM-generated summaries, source snippets, runtime import emulation, full compiler/bundler/framework resolution, server-side assistant session memory, telemetry, hosted evaluation, browser UI, or write-capable MCP behavior.
