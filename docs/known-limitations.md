# RepoLens MCP v0.3 Known Limitations

These limitations are acceptable for v0.3 when they remain explicit, safe, and non-corrupting. Promote a limitation to release-blocking bug work if Context Pack Evaluation or dogfooding shows unsafe assistant guidance, source disclosure risk, stale or misleading expansion, corrupt artifacts, stale graph facts, or unusable workflows.

## Resolution Limits

- RepoLens does not emulate runtime Python imports, installed environments, namespace package edge cases, or dynamic imports.
- RepoLens does not run the TypeScript compiler, package manager, bundler, or framework resolver.
- JavaScript and TypeScript workspace package resolution is partial. Dogfooding found `@dog/lib` classified as third-party in a local fixture even though it is a workspace package.
- Low-confidence fuzzy matches remain candidates only and must not be stored as graph edges.

## Semantic Analysis Limits

- RepoLens does not build deep semantic call graphs, control-flow graphs, data-flow graphs, or taint analysis.
- Impact Analysis is deterministic edit-planning context, not a guarantee of runtime reachability.
- Suggested Reading Order is a bounded heuristic over graph facts and may be shallow for docs/config-only repositories.
- Context Packs are deterministic task-matching and graph-orientation bundles, not semantic embedding search results or AI intent classifiers.
- Structural Summaries are derived from graph facts and structural metadata, not LLM-generated prose summaries.

## Context Pack Limits

- Context Packs are orientation-only. They intentionally omit source snippets, code bodies, function or method signatures, paragraph excerpts, raw comment text, and raw Agent Guidance instruction text.
- Context Pack IDs and item handles are deterministic references, not persisted assistant sessions or serialized source payloads.
- `expand_context` can expand only items returned in the same Context Pack and remains capped at bounded depth and item limits.
- `explain_relevance` explains why an item appeared in a pack; it is not proof that lower-priority context is irrelevant or safe to ignore.
- Broad tasks return bounded packs with breadth warnings, not repository dumps.
- No-match tasks return low-confidence orientation instead of broad fallback context.
- Ambiguous tasks return candidates rather than silently choosing one target.
- Evaluation is local and fixture-based. It is not telemetry, hosted evaluation, or a universal quality score.

## Command And Config Limits

- Candidate commands are recorded as not run. RepoLens never executes package scripts, Make targets, documentation commands, deploy commands, or publish commands.
- Command purpose and risk-bucket detection are conservative. Unknown commands remain candidates only when bounded local evidence supports them.
- Declarative command strings embedded in arbitrary config files may not be promoted into command facts.

## Artifact And Privacy Limits

- `.repolens/` is local cache output and can include sensitive repository metadata even when source text is not mirrored wholesale.
- Redaction targets obvious secret-like paths and values. RepoLens is not a complete secret scanning product.
- Generated graph reports are summaries and may omit details due to caps, truncation, or scanner policy.

## Product Scope Limits

- No write-capable MCP tools.
- No browser UI or graph visualization.
- No HTTP API or HTTP MCP server.
- No AI/LLM-required graph generation, LLM summaries, embeddings, hosted sync, or telemetry.
- No runtime package registry lookups during normal indexing or MCP serving.
- No full framework emulation or runtime package-manager, bundler, or compiler execution during Context Pack generation.
- No persisted Context Pack sessions or server-side assistant memory.
- No PyPI, Docker registry, or hosted publishing automation in v0.3.

## Dogfooding And Evaluation Outcomes Reflected Here

The v0.2 dogfooding report in `docs/dogfood/2026-06-22-v0.2-dogfood.md` identified workspace package resolution gaps, conservative Makefile command classification, and shallow docs/config impact context. These are documented limitations unless follow-up work promotes them to release-blocking bugs.

The v0.3 Context Pack Evaluation suite records release-blocking expectation checks in `tests/fixtures/context_pack/evaluation_manifest.json`. Keep this document aligned when evaluation finds repeated failures to include known relevant files/tests, source disclosure risk, stale-pack misuse, or misleading lower-priority wording.
