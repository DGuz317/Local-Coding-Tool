# RepoLens v0.5 Release Tracker

Issue: #138

Status: accepted scope for v0.5 implementation after v0.4 release signoff.

References:

- `AGENTS.md`
- `docs/adr/0006-layered-code-intelligence-engine.md`
- `docs/repolens-v0.5-roadmap-recommendation.md`

## Theme

```text
Code Intelligence Foundation: one cheap, safe, bounded Assistant Preflight workflow backed by parser, resolver, graph-store, evaluation, and artifact-safety contracts.
```

RepoLens v0.5 should make the assistant-facing first step clearer: ask RepoLens for a bounded preflight before broad repository reads. The release should also define the internal seams needed for later parser, resolver, graph, semantic, and AI expansion without destabilizing the v0.4 trust model.

## Success Criteria

RepoLens v0.5 is successful when assistants have one deterministic, read-only preflight workflow that reduces initial repository exploration while preserving source-disclosure, artifact-safety, and graph-trust boundaries.

Release success requires evidence that:

- parser, resolver, and graph-store foundation contracts are documented or test-locked before implementation slices depend on them;
- Assistant Preflight has a shared CLI/MCP contract with graph freshness, task context, first-read files, likely tests, candidate commands, warnings, evidence, confidence, limits, and truncation metadata;
- MCP behavior remains read-only by default and exposes no write-capable tools;
- candidate commands are discovered but never run by RepoLens, and remain marked as not run;
- Context Pack and preflight outputs remain bounded metadata, not source mirrors;
- local savings metrics and artifact safety audit evidence are available before release readiness;
- real-repo dogfood findings are recorded and distilled into fixtures, known limitations, or follow-up issues.

## Accepted Features

v0.5 accepts these slices:

- Parser Backend Contract and Experimental Hash Gate;
- Resolver Evidence Taxonomy Contract with Candidate Outcome Tracer;
- High-Level Graph Store Seam Smoke;
- Assistant Preflight Contract with focus and budget controls;
- `repolens preflight` CLI;
- MCP `assistant_preflight`;
- local savings metrics in `evaluate-context`;
- `repolens audit-artifacts`;
- install and adoption polish after preflight is stable;
- dogfood evaluation pack;
- final docs, dogfooding, and release readiness.

## Dependency Order

Approved issue flow:

```text
#138 -> #139
#138 -> #140
#138 -> #141
#139, #140 -> #142
#142 -> #143
#143 -> #144
#143 -> #145
#143, #144 -> #146
#143, #144 -> #147
#143, #144, #145, #146 -> #148
#139, #140, #141, #142, #143, #144, #145, #146, #147, #148 -> #149
```

Only issues whose blockers are complete should receive `ready-for-agent`.

Issue #138 is the HITL scope-control issue. Issues #139 through #148 are AFK implementation or evaluation slices. Issue #149 is the final HITL release-readiness slice.

v0.4 release signoff remains a prerequisite for AFK v0.5 implementation work. Issue #128 records that signoff and must stay complete before #139 through #148 are treated as unblocked.

## Child Issues

| Issue | Title | Type | Blocked by |
| --- | --- | --- | --- |
| #139 | Parser Backend Contract And Experimental Hash Gate | AFK | #138 |
| #140 | Resolver Evidence Taxonomy Contract With Candidate Outcome Tracer | AFK | #138 |
| #141 | High-Level Graph Store Seam Smoke | AFK | #138 |
| #142 | Assistant Preflight Contract With Focus And Budget Controls | AFK | #139, #140 |
| #143 | Implement `repolens preflight` CLI | AFK | #142 |
| #144 | Expose MCP `assistant_preflight` | AFK | #143 |
| #145 | Add Local Savings Metrics To `evaluate-context` | AFK | #143 |
| #146 | Add Artifact Safety Audit | AFK | #143, #144 |
| #147 | Install And Adoption Polish | AFK | #143, #144 |
| #148 | Dogfood Evaluation Pack | AFK | #143, #144, #145, #146 |
| #149 | v0.5 Docs, Dogfooding, And Release Readiness | HITL | #139 through #148 |

## Non-Goals

Do not add any of the following in v0.5 unless a maintainer explicitly changes the product boundary:

- hosted service;
- telemetry;
- browser UI or graph visualization;
- embeddings or vector search;
- write-capable MCP tools;
- runtime package-manager, bundler, compiler, framework, or test execution during indexing, Context Pack generation, preflight, or artifact audit;
- runtime package registry lookups;
- LLM-generated graph facts;
- AI Proposals, AI Summary, or semantic prototype output;
- active workflows or command execution;
- real Tree-sitter JS/TS extraction;
- Kuzu implementation or public multi-store support;
- parse cache or worker-pool indexing without benchmark evidence;
- HTTP API or HTTP MCP serving;
- assistant memory or persisted assistant sessions;
- broad framework or language expansion unless dogfood data proves a concrete v0.5 need;
- whole-source disclosure, source snippets, code bodies, function signatures, paragraph excerpts, raw comments, raw Agent Guidance instruction text, or raw config values in assistant-facing output.

## Release Gates

Before v0.5 release readiness, run the full verification gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv run repolens audit-artifacts . --json
uv build --out-dir /tmp/repolens-dist --clear
```

The release gate must include:

- automated verification for unit, integration, lint, format, and type checks;
- Context Pack and preflight evaluation with deterministic expectation-based pass/fail results;
- local savings metrics evidence that explains estimates without telemetry or universal productivity claims;
- artifact audit evidence for no source snippets, no absolute host paths, no raw secrets, no raw Agent Guidance mirroring, bounded artifact sizes, and MCP response contract preservation;
- dogfood evidence for JS/TS workspace, Python package, docs-heavy, config-heavy, ambiguous import, stale graph, and package/workspace tasks;
- regression coverage for v0.3, v0.3.1, and v0.4 safety and graph-trust behavior.

## Maintainer Checkpoints

This tracker is the v0.5 scope-control checkpoint. Maintainer approval is required before AFK implementation slices receive `ready-for-agent`.

After #138 is merged and accepted, downstream v0.5 slices may be unblocked according to the dependency order above, provided the v0.4 signoff prerequisite remains satisfied.
