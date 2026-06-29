# RepoLens v0.4 Release Tracker

Issue: #120

## Theme

```text
Make RepoLens trustworthy across package/workspace repositories.
```

## Success Criteria

RepoLens v0.4 is successful when Context Packs become more trustworthy for package/workspace repositories while preserving the local-first, deterministic, metadata-only safety model.

Release success requires evidence that:

- package identity, workspace membership, package ownership, package dependency, local resolution, relationship candidate, graph-quality warning, resolution strategy, and alias-resolution scope contracts are documented or test-locked;
- package and workspace facts are produced only from explicit local evidence, not conventional directory names alone;
- JavaScript and TypeScript workspace imports and supported TypeScript aliases resolve when explicit package/config evidence is sufficient;
- unresolved, unsupported, and ambiguous package/workspace relationships remain unresolved or appear as bounded candidates with graph-quality warnings;
- Context Packs surface package/workspace orientation as structured metadata without source snippets, code bodies, raw config values, raw comments, raw Agent Guidance text, paragraph excerpts, or absolute host paths;
- Candidate Verification Commands remain marked `found: true` and `run: false`, with command purpose separated from command risk bucket;
- v0.3 and v0.3.1 Context Pack safety and artifact-budget behavior remains regression-protected.

## Dependency Order

Approved issue flow:

```text
#120 -> #121
#121 -> #122
#121 -> #123
#121 -> #124
#122, #123 -> #125
#121, #125, #124 -> #126
#122, #123, #125, #126, #124 -> #127
#127 -> #128
```

Only issues whose blockers are complete should receive `ready-for-agent`.

Issue #121 defines the package evidence contract that downstream v0.4 implementation slices depend on. It must stay blocked until this tracker is accepted, and downstream implementation should not proceed until #121 is merged and accepted.

## Child Issues

| Issue | Title | Type | Blocked by |
| --- | --- | --- | --- |
| #121 | Package Evidence Contract With First Context Pack Tracer | AFK | #120 |
| #122 | Resolve JS/TS Workspace Package Imports From Explicit Evidence | AFK | #121 |
| #123 | Resolve Scoped TypeScript Paths And BaseUrl Aliases | AFK | #121 |
| #124 | Add Command Risk Buckets To Candidate Verification Commands | AFK | #121 |
| #125 | Preserve Ambiguous Package And Import Relationships As Candidates | AFK | #122, #123 |
| #126 | Improve Docs And Config Context Pack Orientation Without Excerpts | AFK | #121, #125, #124 |
| #127 | Expand v0.4 Evaluation Fixtures And Expectation Gates | AFK | #122, #123, #125, #126, #124 |
| #128 | v0.4 Docs, Dogfooding Report, And Release Readiness | HITL | #127 |

## Non-Goals

Do not add any of the following in v0.4 unless a maintainer explicitly changes the product boundary:

- hosted service;
- hosted evaluation;
- telemetry;
- browser UI or graph visualization;
- embeddings or vector search;
- LLM-generated graph facts;
- runtime package-manager, bundler, compiler, framework, or test execution during indexing or Context Pack generation;
- runtime package registry lookups;
- write-capable MCP tools;
- persisted assistant sessions or server-side assistant memory;
- whole-source disclosure;
- source snippets, code bodies, function signatures, paragraph excerpts, raw comments, raw Agent Guidance instruction text, or raw config values in assistant-facing output.

## Release Gates

Before v0.4 release readiness, run the full verification gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/repolens
uv run repolens evaluate-context --json
uv build --out-dir /tmp/repolens-dist --clear
```

The release gate must include:

- automated verification for unit, integration, lint, format, and type checks;
- Context Pack evaluation with expectation-based pass/fail results;
- no-whole-source-disclosure coverage for new package/workspace/candidate/warning output fields;
- JS/TS workspace dogfooding evidence, with important findings distilled into fixtures or known limitations;
- regression coverage for v0.3 and v0.3.1 Context Pack safety and graph-index artifact-budget behavior.

## Maintainer Checkpoints

This tracker is a HITL coordination issue. Maintainer approval is required before #121 is moved out of blocked state.

After #121 is merged and accepted, downstream v0.4 implementation slices may be unblocked according to the dependency order above.
