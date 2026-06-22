# RepoLens MCP v0.2 Known Limitations

These limitations are acceptable for v0.2 when they remain explicit, safe, and non-corrupting. Promote a limitation to release-blocking bug work if dogfooding shows unsafe assistant guidance, corrupt artifacts, source disclosure risk, stale graph facts, or unusable workflows.

## Resolution Limits

- RepoLens does not emulate runtime Python imports, installed environments, namespace package edge cases, or dynamic imports.
- RepoLens does not run the TypeScript compiler, package manager, bundler, or framework resolver.
- JavaScript and TypeScript workspace package resolution is partial. Dogfooding found `@dog/lib` classified as third-party in a local fixture even though it is a workspace package.
- Low-confidence fuzzy matches remain candidates only and must not be stored as graph edges.

## Semantic Analysis Limits

- RepoLens does not build deep semantic call graphs, control-flow graphs, data-flow graphs, or taint analysis.
- Impact Analysis is deterministic edit-planning context, not a guarantee of runtime reachability.
- Suggested Reading Order is a bounded heuristic over graph facts and may be shallow for docs/config-only repositories.

## Command And Config Limits

- Candidate commands are recorded as not run. RepoLens never executes package scripts, Make targets, documentation commands, deploy commands, or publish commands.
- Command purpose detection is conservative. Dogfooding found `make verify` classified as `unknown` in a fixture.
- Declarative command strings embedded in arbitrary config files may not be promoted into command facts.

## Artifact And Privacy Limits

- `.repolens/` is local cache output and can include sensitive repository metadata even when source text is not mirrored wholesale.
- Redaction targets obvious secret-like paths and values. RepoLens is not a complete secret scanning product.
- Generated graph reports are summaries and may omit details due to caps, truncation, or scanner policy.

## Product Scope Limits

- No write-capable MCP tools.
- No browser UI or graph visualization.
- No HTTP API or HTTP MCP server.
- No AI/LLM-required graph generation, embeddings, hosted sync, or telemetry.
- No runtime package registry lookups during normal indexing or MCP serving.
- No PyPI, Docker registry, or hosted publishing automation in v0.2.

## Dogfooding Outcomes Reflected Here

The v0.2 dogfooding report in `docs/dogfood/2026-06-22-v0.2-dogfood.md` identified workspace package resolution gaps, conservative Makefile command classification, and shallow docs/config impact context. These are documented limitations unless follow-up work promotes them to release-blocking bugs.
