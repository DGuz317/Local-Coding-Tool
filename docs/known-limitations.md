# RepoLens MCP v0.7 Known Limitations

These limitations are acceptable for v0.7 when they remain explicit, safe, and non-corrupting. Promote a limitation to release-blocking bug work if Context Pack Evaluation, Semantic Evaluation, artifact audit, or dogfooding shows unsafe assistant guidance, source disclosure risk, stale or misleading preflight, stale semantic inspection, corrupt artifacts, stale graph facts, or unusable workflows.

## Resolution Limits

- RepoLens does not emulate runtime Python imports, installed environments, namespace package edge cases, or dynamic imports.
- RepoLens does not run the TypeScript compiler, package manager, bundler, or framework resolver.
- JavaScript and TypeScript workspace package resolution is evidence-limited, including unsupported workspace declarations, package-manager-specific features outside the documented contract, and workspace scopes without explicit package identity; these remain unresolved or candidates.
- Complex package entrypoints such as conditional export maps, pattern export maps, generated entrypoints, framework conventions, or entrypoints requiring package-manager/bundler execution are not resolved as definitive local edges.
- TypeScript `paths` and `baseUrl` aliases resolve only inside the applicable config subtree and only when they uniquely match scanner-approved in-repository JS/TS modules. Unresolved aliases, unsupported alias patterns, and ambiguous alias targets produce unresolved statuses, candidates, or graph-quality warnings.
- Tree-sitter JS/TS is the default parser backend only when the parser and grammar packages are available. When unavailable, RepoLens falls back to the legacy bounded scanner and emits parser-backend warnings; parser-backed facts may then be absent or shallower.
- JS/TS parser facts are source-free structural metadata. RepoLens does not expose full import lines, source expressions, function signatures, code bodies, raw comments, or absolute host paths through assistant-facing parser facts.
- Lockfile-only evidence does not create package ownership facts. Lockfiles may support candidates only when they clearly map to local workspace packages, and ownership still requires explicit package/config evidence.
- Low-confidence fuzzy matches remain candidates only and must not be stored as graph edges.

## Semantic Analysis Limits

- v0.7 Python semantic facts are experimental, source-free candidate metadata outside the stable graph contract. They do not affect Canonical Graph Hash, default Context Pack IDs, stable graph validation, default MCP output, default Assistant Preflight output, or default Context Pack output.
- v0.7 Python semantic analysis is limited to deterministic function-level CFG and lexical binding metadata.
- Python CFG facts are function-level structural metadata for bounded constructs such as `if`, loops, `return`, `raise`, sequential `with` blocks, and limited `try` shapes. They are not runtime reachability proof, data-flow analysis, taint analysis, type inference, exception modeling, or a deep semantic call graph.
- Python lexical binding facts describe deterministic AST-level local definitions, parameters, imports, assignments, references, unresolved names, shadowing, free-variable candidates, `global`, and `nonlocal` declarations. They do not prove runtime values, object identity, import execution, descriptor behavior, monkeypatching, reflection, decorators, metaclasses, generated attributes, or dynamic scope effects.
- Unsupported or dynamic Python constructs produce warnings, unresolved statuses, or unsupported markers instead of guessed facts. This includes complex `match` behavior, async scheduling, generators, `yield`, `await`, dynamic `exec`/`eval`, dynamic imports, runtime mutation of `globals()` or `locals()`, and cross-module type/runtime inference.
- Runtime dispatch, monkeypatching, metaclasses, decorators with dynamic effects, reflection, imports with runtime side effects, and framework behavior are not executed or inferred.
- Indexed `semantic-inspect` reads `.repolens/semantic.sqlite` by default. Missing, stale, or incompatible artifacts report artifact status and freshness; RepoLens does not silently parse live source unless the user passes explicit `--from-source`.
- `semantic-inspect --from-source` is a non-persistent live debug mode. It does not write `graph.sqlite`, `.repolens/semantic.sqlite`, `semantic.jsonl`, Canonical Graph Hash inputs, default Context Pack IDs, stable graph validation inputs, or default MCP output.
- `semantic.jsonl`, when generated for debug/evaluation, is bounded, deterministic, source-free, and audit-covered. It is not the stable semantic database contract.
- Semantic artifacts must remain source-free and must not mirror code bodies, function signatures, raw comments, raw docstrings, raw string literals, secrets, or absolute host paths.
- Optional Context Pack semantic hints are included only behind explicit `include_experimental_semantic_hints` opt-in and remain experimental, bounded, source-free metadata; default Context Packs remain deterministic graph-orientation bundles, not semantic embedding search results or AI intent classifiers.
- Call Chain Facts are shallow parser-derived structural metadata with method names, receiver shape, and bounded line ranges. They are not runtime reachability proof, data-flow evidence, framework lifecycle evidence, or a semantic call graph.
- Framework Route Hints are deterministic local hints, not runtime route proof. RepoLens does not run Next.js, emulate framework loaders, inspect build output, or execute package-manager, bundler, compiler, framework, or test commands to discover routes.
- Impact Analysis is deterministic edit-planning context, not a guarantee of runtime reachability.
- Suggested Reading Order is a bounded heuristic over graph facts and may be shallow for docs/config-only repositories.
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
- No full framework emulation or runtime package-manager, bundler, compiler, framework, or test execution during indexing, Context Pack generation, preflight, or artifact audit.
- No persisted Context Pack sessions or server-side assistant memory.
- No PyPI, Docker registry, or hosted publishing automation in v0.7.
- No PyPI, Docker registry, or hosted publishing automation in v0.6 remains true for the v0.7 readiness branch.

## Dogfooding And Evaluation Outcomes Reflected Here

The v0.2 dogfooding report in `docs/dogfood/2026-06-22-v0.2-dogfood.md` identified workspace package resolution gaps, conservative Makefile command classification, and shallow docs/config impact context. These are documented limitations unless follow-up work promotes them to release-blocking bugs.

The v0.4 Context Pack Evaluation suite records release-blocking expectation checks in `tests/fixtures/context_pack/evaluation_manifest.json`. Keep this document aligned when evaluation finds repeated failures to include known relevant files/tests, source disclosure risk, stale-pack misuse, misleading lower-priority wording, package/workspace overclaiming, missing Relationship Candidates, missing Graph Quality Warnings, docs/config orientation gaps, or command risk bucket regressions.

The v0.5 dogfood evaluation pack in `docs/dogfood/2026-07-02-v0.5-dogfood-evaluation-pack.md` adds Assistant Preflight, local savings metrics, and artifact audit scenarios. Keep this document aligned when dogfooding finds repeated stale graph confusion, over-broad focus hints, misleading budget metadata, unsafe artifact output, or candidate commands that could be mistaken as run or recommended for automatic execution.

No PyPI, Docker registry, or hosted publishing automation in v0.5 was accepted as a release boundary and remains unchanged in v0.6.

The v0.6 dogfood evaluation pack in `docs/dogfood/2026-07-06-v0.6-dogfood-evaluation-pack.md` adds release-blocking checks for JS/TS call chains, re-export behavior, workspace imports, route hints, stale graph behavior, and no-source-disclosure negatives. Parser timing and file-count evidence are bounded local fixture evidence only; use them to document limitations, not to justify parse caches, worker pools, indexing parallelism, telemetry, package-manager execution, compiler execution, or framework execution.

The v0.7 semantic evaluation suite in `tests/fixtures/semantic_evaluation` adds release-blocking checks for deterministic Python CFG, lexical binding, unsupported/uncertain constructs, no-source-disclosure negatives, stable identity exclusion, and semantic debug/evaluation export audit behavior. Use those results to document limitations, not to broaden into data-flow, taint, type inference, dynamic runtime emulation, package-manager execution, compiler execution, framework execution, AI summaries, embeddings, telemetry, or hosted services.
