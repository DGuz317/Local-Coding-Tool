# RepoLens MCP v0.2 Release Tracker

Release theme:

```text
Make RepoLens reliable on real repositories before making it deeply semantic.
```

Release integration branch: `feature/repolens-v0.2`

GitHub umbrella tracker: #35

## Source Documents

- `docs/repolens-v0.2-plan.md`
- `docs/repolens-v0.2-planning-interview-summary.md`
- `docs/repolens-v0.2-issue-breakdown-feedback.md`
- `docs/repolens-v0.2-issue-breakdown.md`
- `CONTEXT.md`
- `docs/adr/0001-standardize-mcp-envelope.md`
- `docs/adr/0002-edge-contract-storage.md`

## Release-Blocking P0 Work

- [x] #35 RepoLens MCP v0.2 roadmap and release criteria
- [ ] #36 Add Edge Contract storage and duplicate edge normalization
- [ ] #37 Add Canonical Graph Hash, Graph Validation, and rebuild guardrails
- [ ] #38 Resolve Python local imports deterministically
- [ ] #39 Resolve JS/TS relative imports and harden simple aliases
- [ ] #40 Normalize Resolution Strategy and candidate-only ambiguity handling
- [ ] #41 Store Related Test relationships with confidence and evidence
- [ ] #42 Group Impact Analysis and enforce Target Expansion traversal boundaries
- [ ] #43 Improve Suggested Reading Order ranking and command context
- [ ] #44 Add shared MCP envelope foundation and contract tests
- [ ] #45 Migrate MCP tools to standardized envelope, errors, pagination, and stdio discipline
- [ ] #46 Add file-level Selective Update planner and graph replacement path
- [ ] #47 Add Selective Update cleanup tests and generated benchmark fixture
- [ ] #48 Add shared Redaction Policy and scanner/security fixtures
- [ ] #49 Add MCP No Whole-Source Disclosure and raw text safety tests
- [ ] #52 Add Dogfooding Reports and regression fixture process
- [ ] #53 Add minimal CI and isolated install smoke
- [ ] #54 Add v0.2 user docs, assistant docs, release checklist, and known limitations

## Non-Blocking P1 Work

- [ ] #50 Improve Package Boundary, workspace, and command grouping awareness
- [ ] #51 Add optional Parser Backend experiment behind default-stable behavior

Promote #50 only if dogfooding proves package/workspace gaps are release-blocking. #51 remains optional and must not destabilize default parser behavior.

## Dependency Notes

- #36 starts the P0 implementation path after the roadmap tracker exists.
- #37 depends on #36 and unlocks resolver, selective update, redaction, and optional parser work.
- #44 depends on #36 and can start before impact analysis and reading order migration.
- #45 depends on #42, #43, and #44.
- #52 depends on #45, #47, and #49, and does not depend on P1 package/workspace work.
- #54 depends on dogfooding, minimal CI, and final MCP contract behavior.

## Release Criteria

Do not cut a v0.2 release until all release-blocking P0 items above are complete and the release gate has evidence for:

- Deterministic `index` and `update` behavior on fixture repositories.
- Read-like `status` behavior that does not mutate artifacts.
- Graph schema compatibility checks and validation before artifact replacement.
- Reference resolution with strategy, confidence, evidence, and candidate-only ambiguity handling.
- Impact analysis grouped by dependencies, dependents, tests, docs, configs, commands, and risks where available.
- Suggested reading order with ranking reasons, bounded output, and likely tests when task-relevant.
- Standardized MCP envelopes, structured errors, stale/missing graph handling, caps, truncation, and pagination where applicable.
- No Whole-Source Disclosure through MCP tools; raw text search returns only bounded sanitized previews.
- Redaction and scanner safety for secret-looking paths, secret-like metadata, command strings, and path traversal inputs.
- Candidate verification commands are stored and shown as not run, never as automatically executed recommendations.
- Selective Update removes stale facts for deleted or unparseable files and falls back to full rebuild when safety checks require it.
- Full verification passes: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/repolens`.
- Minimal CI/build/install smoke passes as defined by #53.
- Dogfooding reports and regression fixtures are complete as defined by #52.
- Known limitations and release-readiness docs are explicit as defined by #54.

## Dogfooding Expectations

Dogfooding is release-blocking, but it must not vendor third-party repository snapshots into this repo. Commit only reports, distilled fixtures, and known limitations.

Required dogfooding coverage:

- RepoLens on itself.
- At least one representative Python repository.
- At least one representative JS/TS repository.
- At least one mixed docs/config repository.

Each dogfooding report should capture:

- Graph quality issues.
- Resolver misses, false positives, and false negatives.
- Impact analysis and reading-order friction.
- MCP response usability issues.
- Index/update performance and failure modes.
- Bugs converted into regression fixtures or explicitly deferred as known limitations.

## Known Limitation Policy

Known limitations are acceptable when they are explicit, safe, and not release-blocking reliability failures.

Document limitations instead of silently resolving when behavior would require:

- Runtime Python import emulation.
- Full TypeScript compiler, package manager, bundler, or framework resolution.
- Deep semantic call graphs, control-flow graphs, data-flow analysis, or taint analysis.
- AI/LLM-required graph generation, embeddings, hosted services, telemetry, browser UI, or write-capable MCP tools.
- Publishing automation for PyPI, Docker registries, or hosted release channels.

Promote a limitation to P0 bug work when dogfooding shows it causes unsafe assistant guidance, corrupt graph artifacts, source disclosure risk, stale graph facts, or unusable release-blocking workflows.

## Tracker Maintenance

- Keep this file and #35 aligned when slices close or scope changes.
- Keep P0/P1 separation visible in both places.
- Add comments to #35 for material decisions instead of burying release scope in closed slice issues.
- Close #35 only after the v0.2 release gate is satisfied or the release scope is explicitly abandoned.
