# RepoLens MCP v0.5 Known Limitations

These limitations are acceptable for v0.5 when they remain explicit, safe, and non-corrupting. Promote a limitation to release-blocking bug work if Context Pack Evaluation or dogfooding shows unsafe assistant guidance, source disclosure risk, stale or misleading preflight or expansion, corrupt artifacts, stale graph facts, or unusable workflows.

## Resolution Limits

- RepoLens does not emulate runtime Python imports, installed environments, namespace package edge cases, or dynamic imports.
- RepoLens does not run the TypeScript compiler, package manager, bundler, or framework resolver.
- JavaScript and TypeScript workspace package resolution is evidence-limited, including unsupported workspace declarations, package-manager-specific features outside the documented contract, and workspace scopes without explicit package identity; these remain unresolved or candidates.
- Complex package entrypoints such as conditional export maps, pattern export maps, generated entrypoints, framework conventions, or entrypoints requiring package-manager/bundler execution are not resolved as definitive local edges.
- TypeScript `paths` and `baseUrl` aliases resolve only inside the applicable config subtree and only when they uniquely match scanner-approved in-repository JS/TS modules. Unresolved aliases, unsupported alias patterns, and ambiguous alias targets produce unresolved statuses, candidates, or graph-quality warnings.
- Lockfile-only evidence does not create package ownership facts. Lockfiles may support candidates only when they clearly map to local workspace packages, and ownership still requires explicit package/config evidence.
- Low-confidence fuzzy matches remain candidates only and must not be stored as graph edges.

## Semantic Analysis Limits

- RepoLens does not build deep semantic call graphs, control-flow graphs, data-flow graphs, or taint analysis.
- Impact Analysis is deterministic edit-planning context, not a guarantee of runtime reachability.
- Suggested Reading Order is a bounded heuristic over graph facts and may be shallow for docs/config-only repositories.
- Context Packs are deterministic task-matching and graph-orientation bundles, not semantic embedding search results or AI intent classifiers.
- Structural Summaries are derived from graph facts and structural metadata, not LLM-generated prose summaries.

## Context Pack Limits

- Assistant Preflight is a bounded orientation workflow before broad file reads, not a source mirror, semantic planner, or command runner.
- Focus hints and budget controls deterministically narrow ranking and output size, but they do not guarantee that every relevant file or test appears in the first response.
- Stale or missing graph handling is explicit: RepoLens reports freshness and warnings, while MCP tools remain read-only and do not rebuild artifacts.
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
- No PyPI, Docker registry, or hosted publishing automation in v0.5.

## Dogfooding And Evaluation Outcomes Reflected Here

The v0.2 dogfooding report in `docs/dogfood/2026-06-22-v0.2-dogfood.md` identified workspace package resolution gaps, conservative Makefile command classification, and shallow docs/config impact context. These are documented limitations unless follow-up work promotes them to release-blocking bugs.

The v0.4 Context Pack Evaluation suite records release-blocking expectation checks in `tests/fixtures/context_pack/evaluation_manifest.json`. Keep this document aligned when evaluation finds repeated failures to include known relevant files/tests, source disclosure risk, stale-pack misuse, misleading lower-priority wording, package/workspace overclaiming, missing Relationship Candidates, missing Graph Quality Warnings, docs/config orientation gaps, or command risk bucket regressions.

The v0.5 dogfood evaluation pack in `docs/dogfood/2026-07-02-v0.5-dogfood-evaluation-pack.md` adds Assistant Preflight, local savings metrics, and artifact audit scenarios. Keep this document aligned when dogfooding finds repeated stale graph confusion, over-broad focus hints, misleading budget metadata, unsafe artifact output, or candidate commands that could be mistaken as run or recommended for automatic execution.
